"""Language-conditioned action-chunking policy with pointer-grounded action head.

    [QUERY] [w1 … w12] [obj1 … obj6] [PROPRIO] ──► TransformerEncoder (pre-norm)
        │                                  │
        │   pointer heads: QUERY · obj_i ──┴─► P(source = i), P(destination = i)  (or "none")
        │                                         │ soft attention weights
        ▼                                         ▼
    task embedding (QUERY)  +  Σ_i P(src=i)·feat_i  +  Σ_i P(dst=i)·feat_i  +  proprio
        └──────────────────────────► action MLP ──► HORIZON × 7 actions, P(done)

The transformer does the language understanding: which words refer to which perceived
object (word embeddings are shared between instruction tokens and object label tokens,
and colour features let "red" find the red object even without a label). The pointer
weights are soft and differentiable, so the whole network trains end to end from the
imitation loss; the precise geometry of the chosen objects reaches the action MLP
directly instead of having to survive several attention layers. No rules at inference.
"""

from __future__ import annotations

import torch
from torch import nn

from .common import ACT_DIM, HORIZON, MAX_OBJECTS, MAX_TOKENS, OBJ_DIM, PAD, PROPRIO_DIM


def _mlp(i: int, h: int, o: int, layers: int = 2) -> nn.Sequential:
    mods, d = [], i
    for _ in range(layers):
        mods += [nn.Linear(d, h), nn.GELU()]
        d = h
    return nn.Sequential(*mods, nn.Linear(d, o))


class ActPolicyNet(nn.Module):
    def __init__(self, vocab_size: int, d_model: int = 96, heads: int = 4, layers: int = 2, hidden: int = 256,
                 dropout: float = 0.05) -> None:
        super().__init__()
        self.cfg = dict(vocab_size=vocab_size, d_model=d_model, heads=heads, layers=layers, hidden=hidden,
                        dropout=dropout)
        self.word = nn.Embedding(vocab_size, d_model, padding_idx=PAD)
        self.tok_pos = nn.Parameter(torch.zeros(1, MAX_TOKENS, d_model))
        self.kind = nn.Embedding(4, d_model)  # 0 query, 1 text, 2 object, 3 proprio
        self.query = nn.Parameter(torch.zeros(1, 1, d_model))
        self.obj_in = _mlp(OBJ_DIM, d_model, d_model, 1)
        self.prop_in = _mlp(PROPRIO_DIM, d_model, d_model, 1)
        layer = nn.TransformerEncoderLayer(d_model, heads, 2 * d_model, dropout, batch_first=True, norm_first=True,
                                           activation="gelu")
        self.encoder = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.norm = nn.LayerNorm(d_model)
        self.src_q, self.dst_q = nn.Linear(d_model, d_model), nn.Linear(d_model, d_model)
        self.none_logit = nn.Linear(d_model, 2)  # "no source" / "no destination" scores
        self.act_mlp = _mlp(d_model + 2 * OBJ_DIM + PROPRIO_DIM, hidden, HORIZON * ACT_DIM + 1, 3)
        nn.init.normal_(self.tok_pos, std=0.02)
        nn.init.normal_(self.query, std=0.02)

    def forward(self, tokens, obj_feat, obj_label, obj_mask, proprio):
        b = tokens.shape[0]
        t = self.word(tokens) + self.tok_pos + self.kind.weight[1]
        o = self.obj_in(obj_feat) + self.word(obj_label) + self.kind.weight[2]
        p = (self.prop_in(proprio) + self.kind.weight[3]).unsqueeze(1)
        q = self.query.expand(b, -1, -1) + self.kind.weight[0]
        zeros = torch.zeros(b, 1, dtype=torch.bool, device=tokens.device)
        pad = torch.cat([zeros, tokens == PAD, ~obj_mask, zeros], dim=1)
        h = self.norm(self.encoder(torch.cat([q, t, o, p], dim=1), src_key_padding_mask=pad))
        hq, ho = h[:, 0], h[:, 1 + MAX_TOKENS: 1 + MAX_TOKENS + MAX_OBJECTS]

        scale = hq.shape[-1] ** -0.5
        neg = torch.finfo(hq.dtype).min
        none = self.none_logit(hq)
        src = torch.einsum("bd,bkd->bk", self.src_q(hq), ho).mul(scale).masked_fill(~obj_mask, neg)
        dst = torch.einsum("bd,bkd->bk", self.dst_q(hq), ho).mul(scale).masked_fill(~obj_mask, neg)
        src = torch.cat([src, none[:, :1]], dim=1)  # last index = NONE_SLOT
        dst = torch.cat([dst, none[:, 1:]], dim=1)

        w_src = torch.softmax(src, -1)[:, :MAX_OBJECTS]
        w_dst = torch.softmax(dst, -1)[:, :MAX_OBJECTS]
        f_src = torch.einsum("bk,bkf->bf", w_src, obj_feat)  # soft-selected object features
        f_dst = torch.einsum("bk,bkf->bf", w_dst, obj_feat)
        out = self.act_mlp(torch.cat([hq, f_src, f_dst, proprio], dim=-1))
        actions = out[:, :-1].view(b, HORIZON, ACT_DIM)
        done = out[:, -1]
        return actions, done, src, dst
