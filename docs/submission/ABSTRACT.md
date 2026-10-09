# Abstract: VLA Robot Dashboard

Programming an industrial robot still means writing code for every new task. We built a Vision-Language-Action (VLA) system that lets an operator simply type what they want, such as "put the red cube on the blue cylinder", and have a robot arm carry it out. The prototype runs a Yaskawa Motoman GP7 in simulation, built from the vendor's CAD meshes and kinematics on the MuJoCo and PyBullet physics engines, with real grasping and stacking.

A camera feeds a perception pipeline: RT-DETR detects objects and people, RF-DETR segments them and PaddleOCR reads their labels. Detections are lifted into 3D so the instruction's words match real positions. A language-conditioned transformer policy, trained by imitation learning on thousands of demonstrations from a rule-based expert planner, then chooses the source and destination objects and outputs the next eight motion commands. No hand-written rules run at decision time.

Safety is enforced by a single robot controller: a latching emergency stop, an automatic hold when a person is in view, a watchdog, inference timeouts and per-step motion limits. A PyQt6 dashboard shows the live camera with the model's chosen targets, telemetry and logs, and retrains the policy without stopping the robot.

In closed-loop tests on new random layouts, the shipped model completes 96.7% of tasks on the GP7 in PyBullet, 93.3% with phrasings never seen in training, and refuses 100% of requests for objects that are not present. The policy decides in about 1 ms on a CPU and the control loop holds 20 Hz. The main remaining limitation is balancing objects on a ball. The approach extends to industrial pick-and-place, kitting, sorting and machine tending.

## Keywords

Vision-Language-Action, Physical AI, Robot manipulation, Imitation learning, Transformer policy, Natural language instructions, Object detection, Instance segmentation, MuJoCo, Yaskawa GP7, Robot safety, PyQt6
