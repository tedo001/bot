import type * as React from 'react';

export type RunStatus = 'idle' | 'loading' | 'running' | 'succeeded' | 'stopped' | 'safety_hold' | 'failed';
export type IconName = 'play' | 'pause' | 'stop' | 'step' | 'reset' | 'home' | 'estop' | 'robot' | 'gripper' | 'jog' | 'axes' | 'cube' | 'target' | 'camera' | 'eye' | 'layers' | 'program' | 'shield' | 'policy' | 'train' | 'chart' | 'terminal' | 'sliders' | 'warning' | 'check' | 'lock' | 'chevron';

/** 24px stroke icon drawn with currentColor. */
export interface IconProps { name: IconName; size?: number; label?: string; className?: string; style?: React.CSSProperties }
export declare function Icon(props: IconProps): React.ReactElement;

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'quiet' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  icon?: IconName;
  /** Keyboard shortcut shown after the label, e.g. "Ctrl+↵". */
  kbd?: string;
}
export declare function Button(props: ButtonProps): React.ReactElement;

export interface SegmentedOption { value: string; label: React.ReactNode; icon?: IconName; disabled?: boolean }
export interface SegmentedProps { options: Array<string | SegmentedOption>; value?: string; defaultValue?: string; onChange?: (value: string) => void; size?: 'sm' | 'md'; label?: string; disabled?: boolean; className?: string }
export declare function Segmented(props: SegmentedProps): React.ReactElement;

export interface ToggleProps { label: React.ReactNode; hint?: React.ReactNode; checked?: boolean; defaultChecked?: boolean; onChange?: (checked: boolean) => void; disabled?: boolean; className?: string }
export declare function Toggle(props: ToggleProps): React.ReactElement;

export interface RunControlsProps {
  status: RunStatus;
  onRun?: () => void; onStep?: () => void; onPause?: () => void; onStop?: () => void; onReset?: () => void;
  /** Blocks Run and Step and is shown under the buttons, e.g. "Safety config changed: apply to run". */
  disabledReason?: string;
  className?: string;
}
export declare function RunControls(props: RunControlsProps): React.ReactElement;

export interface StatusPillProps { status: RunStatus; size?: 'md' | 'lg'; label?: string; className?: string }
export declare function StatusPill(props: StatusPillProps): React.ReactElement;

export interface EStopProps {
  engaged?: boolean; defaultEngaged?: boolean; onChange?: (engaged: boolean) => void;
  /** Bind Esc to toggle (default true). Turn off only when another EStop on the page owns Esc. */
  hotkey?: boolean;
  /** 48px button without the state text, for the ribbon. */
  compact?: boolean;
  className?: string;
}
export declare function EStop(props: EStopProps): React.ReactElement;

export interface BannerProps { kind: 'estop' | 'hold' | 'info'; title: string; message?: React.ReactNode; action?: { label: string; onClick?: () => void }; icon?: IconName; className?: string }
export declare function Banner(props: BannerProps): React.ReactElement;

export interface SafetyCheck { name: string; detail?: string; value?: string; state?: 'ok' | 'changed' | 'fault' }
export interface SafetyChecksProps { checks: SafetyCheck[]; selected?: number; onSelect?: (index: number) => void; className?: string }
export declare function SafetyChecks(props: SafetyChecksProps): React.ReactElement;

export interface InstructionBoxProps {
  value?: string; defaultValue?: string; onChange?: (text: string) => void;
  /** Called with the trimmed text on Ctrl+Enter when it validates. */
  onRun?: (text: string) => void;
  examples?: string[]; error?: string; rows?: number; disabled?: boolean; className?: string;
}
export declare function InstructionBox(props: InstructionBoxProps): React.ReactElement;
/** Same rules as the app's InstructionPayload: 3–512 characters, words, no control characters. Returns the message or null. */
export declare function validateInstruction(text: string): string | null;

export interface TaskPhase { name: string; detail?: string }
export interface TaskPlanProps {
  phases: Array<string | TaskPhase>;
  /** Index of the phase being executed. */
  current?: number;
  status?: 'running' | 'done' | 'failed' | 'hold';
  source?: string; destination?: string;
  /** The policy's done probability, 0–1. */
  doneProb?: number;
  message?: string; className?: string;
}
export declare function TaskPlan(props: TaskPlanProps): React.ReactElement;

export interface ProgramLine { op?: string; text: string; kind?: 'motion' | 'gripper' | 'detect' | 'wait' | 'flow' | 'language' | 'comment' }
export interface ProgramListProps { name?: string; lines: Array<string | ProgramLine>; current?: number; selected?: number; onSelect?: (index: number) => void; status?: RunStatus; palette?: boolean; onInsert?: (op: string) => void; className?: string }
export declare function ProgramList(props: ProgramListProps): React.ReactElement;

export interface JogAxis { name: string; label?: string; min: number; max: number; value: number; unit?: 'deg' | 'mm'; axis?: 'x' | 'y' | 'z' }
export interface JogPanelProps {
  frame?: 'joint' | 'world' | 'tool' | 'user'; defaultFrame?: 'joint' | 'world' | 'tool' | 'user'; onFrameChange?: (f: string) => void;
  /** Defaults to the GP7's six joints and limits. */
  joints?: JogAxis[]; cartesian?: JogAxis[];
  deadman?: boolean; onDeadmanChange?: (held: boolean) => void;
  speed?: number; onSpeedChange?: (pct: number) => void;
  onJog?: (e: { frame: string; axis: string; value: number }) => void;
  onRecord?: () => void; onHome?: () => void;
  /** Locks the pendant and says why, e.g. "Jog is off while RUNNING". */
  disabledReason?: string;
  className?: string;
}
export declare function JogPanel(props: JogPanelProps): React.ReactElement;

export interface PoseReadoutProps {
  pose: { x?: number; y?: number; z?: number; w?: number; p?: number; r?: number };
  gripper?: { opening: number; holding?: string | null };
  frame?: string; linearUnit?: 'm' | 'mm';
  /** Age of the data when it is not fresh, e.g. "1.2 s". */
  stale?: string;
  className?: string;
}
export declare function PoseReadout(props: PoseReadoutProps): React.ReactElement;

export interface CellNode { id: string; label: string; icon?: IconName; meta?: string; badge?: 'src' | 'dst'; hidden?: boolean; locked?: boolean; open?: boolean; children?: CellNode[] }
export interface CellTreeProps { nodes: CellNode[]; selected?: string; defaultSelected?: string; onSelect?: (id: string) => void; defaultOpen?: boolean; label?: string; className?: string }
export declare function CellTree(props: CellTreeProps): React.ReactElement;

export interface PropertyField { label: string; value?: string | number | boolean; unit?: string; kind?: 'number' | 'text' | 'select' | 'toggle'; options?: string[]; axis?: 'x' | 'y' | 'z' }
export interface PropertyInspectorProps { title?: string; subtitle?: string; icon?: IconName; sections: Array<{ title: string; columns?: number; fields: PropertyField[] }>; className?: string }
export declare function PropertyInspector(props: PropertyInspectorProps): React.ReactElement;

export interface SceneObject { id?: string; label?: string; shape: 'cube' | 'cylinder' | 'sphere'; x: number; y: number; color?: string; mark?: 'src' | 'dst'; score?: number; mask?: boolean }
export interface ViewportProps {
  mode?: '3d' | 'camera';
  objects?: SceneObject[];
  overlays?: { boxes?: boolean; masks?: boolean; skeleton?: boolean; ocr?: boolean; hud?: boolean };
  hud?: string;
  /** TCP position in metres, world frame. */
  tcp?: [number, number, number];
  banner?: React.ReactNode; toolbar?: React.ReactNode; showCube?: boolean; showTriad?: boolean;
  height?: number | string; label?: string;
  /** Floating windows (a Panel with floating) positioned over the scene. */
  children?: React.ReactNode;
  className?: string;
}
export declare function Viewport(props: ViewportProps): React.ReactElement;

export interface TelemetryMetric { label: string; value: React.ReactNode; unit?: string; note?: string; tone?: 'ok' | 'hold' }
export interface TelemetryProps { metrics?: TelemetryMetric[]; stages?: Record<string, number>; budgetMs?: number; className?: string }
export declare function Telemetry(props: TelemetryProps): React.ReactElement;

export interface LogLine { t: string; level?: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'; src?: string; msg: string }
export interface ConsoleProps { lines: LogLine[]; filter?: 'all' | 'warn' | 'error'; onFilterChange?: (f: string) => void; height?: number; className?: string }
export declare function Console(props: ConsoleProps): React.ReactElement;

export interface TrainingProgressProps {
  status?: 'idle' | 'running' | 'done' | 'failed';
  /** 0 demonstrations, 1 epochs, 2 evaluation. */
  stage?: number;
  progress?: number; message?: string;
  preset?: 'quick' | 'full'; onPresetChange?: (p: string) => void;
  stages?: Array<{ name: string; detail?: string }>;
  onTrain?: () => void; onStop?: () => void; className?: string;
}
export declare function TrainingProgress(props: TrainingProgressProps): React.ReactElement;

export interface ModelEntry { name: string; file: string; trained?: string; sim?: number; pybullet?: number; mujoco?: number; driving?: boolean }
export interface ModelRegistryProps { models: ModelEntry[]; selected?: string; onSelect?: (file: string) => void; onActivate?: (file: string) => void; className?: string }
export declare function ModelRegistry(props: ModelRegistryProps): React.ReactElement;

export interface RibbonTool { icon: IconName; label: string; primary?: boolean; danger?: boolean; disabled?: boolean; title?: string; onClick?: () => void }
export interface RibbonProps {
  product?: string;
  tabs: Array<{ id: string; label: string; icon?: IconName }>;
  active?: string; onTabChange?: (id: string) => void;
  groups: Array<{ label: string; tools: RibbonTool[] }>;
  meta?: React.ReactNode;
  /** Right end of the tool row: the compact EStop and the StatusPill. */
  right?: React.ReactNode;
  className?: string;
}
export declare function Ribbon(props: RibbonProps): React.ReactElement;

export interface PanelProps { title: string; icon?: IconName; meta?: React.ReactNode; actions?: React.ReactNode; footer?: React.ReactNode; collapsible?: boolean; defaultOpen?: boolean; flush?: boolean; floating?: boolean; style?: React.CSSProperties; className?: string; children?: React.ReactNode }
export declare function Panel(props: PanelProps): React.ReactElement;

export interface StatusBarItem { label?: string; value: React.ReactNode; icon?: IconName; tone?: 'ok' | 'hold' | 'danger'; push?: boolean }
export interface StatusBarProps { status?: RunStatus; items: StatusBarItem[]; className?: string }
export declare function StatusBar(props: StatusBarProps): React.ReactElement;

declare global {
  interface Window {
    VLAStudio: {
      Icon: typeof Icon; Button: typeof Button; Segmented: typeof Segmented; Toggle: typeof Toggle; RunControls: typeof RunControls;
      StatusPill: typeof StatusPill; EStop: typeof EStop; Banner: typeof Banner; SafetyChecks: typeof SafetyChecks;
      InstructionBox: typeof InstructionBox; TaskPlan: typeof TaskPlan; ProgramList: typeof ProgramList;
      JogPanel: typeof JogPanel; PoseReadout: typeof PoseReadout;
      CellTree: typeof CellTree; PropertyInspector: typeof PropertyInspector; Viewport: typeof Viewport;
      Telemetry: typeof Telemetry; Console: typeof Console; TrainingProgress: typeof TrainingProgress; ModelRegistry: typeof ModelRegistry;
      Ribbon: typeof Ribbon; Panel: typeof Panel; StatusBar: typeof StatusBar;
      validateInstruction: typeof validateInstruction; ICON_NAMES: IconName[];
    };
  }
}
