from dis import Instruction
import json
from operator import call
import os
import argparse
import re
from turtle import pd
from templates import (
    milestone_task_instruction_template,
    milestone_task_instruction_template_no_teach,
    milestone_task_answer_template,
    main_task_instruction_template,
    main_task_instruction_template_no_teach,
    main_task_answer_template,
    main_task_reasoning_template,
    step_task_instruction_template
)
from templates import (
    main_task_system_prompt_template_v0,
    milestone_task_system_prompt_template,
    main_task_system_prompt_template_v1
)
from frame_extractor import VideoFrameExtractor
import pdb

VIDEO_DIR = "/data/lhx/LLaMA-Factory/data/ui_zero/data"
# Known default click-like action prefixes from metadata
DEFAULT_ACTION_MAP = {
    "LClick at": "left_click",
    "RClick at": "right_click",
    "DClick at": "double_click",
    "MouseDown": "mouse_down",
    "MouseUp": "mouse_up",
    "ScrollUp at": "scroll_up",
    "ScrollDown at": "scroll_down",
    "LDoubleClick at": "left_double_click",
    "Wait": "wait",
    "Key Press": "press_key",
    "LongPressStart": "key_down",
    "LongPressEnd": "key_up",
    "LDrag": "drag_to"
}
ACTIONS_WITH_NO_ARG = ["Wait"]
ACTIONS_WITH_ONE_COORD = ["LClick at", "RClick at", "DClick at", "ScrollUp at", "ScrollDown at", "LDoubleClick at"]
ACTIONS_WITH_KEYBOARD = ["Key Press", "LongPressStart", "LongPressEnd"]
ACTIONS_WITH_MANY_COORDS = ["LDrag"]

# ANSI color/symbol helpers for more visible CLI output
_C_G = "\033[92m"  # green
_C_Y = "\033[93m"  # yellow
_C_R = "\033[91m"  # red
_C_B = "\033[94m"  # blue
_C_N = "\033[0m"   # reset
SYMBOL_CHECK = f"{_C_G}✓{_C_N}"
SYMBOL_ARROW = f"{_C_Y}→{_C_N}"
SYMBOL_CROSS = f"{_C_R}✗{_C_N}"
SYMBOL_INFO = f"{_C_B}ℹ{_C_N}"


# NOTE: 仿照Claude添加system prompt
# NOTE: 修改输入输出格式为tool call格式
# NOTE: 添加step-task
# TODO: 后续考虑将roadmap改为tool call的形式
# TODO: 后续考虑补充传入更多关键帧信息
# TODO: 考虑修改roadmap为replace的格式


class RawTraceProcessor:
    def __init__(self, raw_data_dir, task_id, img_save_dir):
        """ Initialize the RawDataProcessor with the directory containing raw data. """
        self.raw_data_dir = os.path.join(raw_data_dir, "trace_hierarchy_service")
        self.task_id = task_id
        self.task_description, self.milestones, self.trajectory, self.video_url = self.load_trace_data()
        self.data = []
        self.extractor = VideoFrameExtractor(self.video_url)
        self.img_save_dir = img_save_dir

    def load_trace_data(self):
        """ Load and parse the trace data from the specified directory. """
        trace_data_path = ""
        for filename in os.listdir(self.raw_data_dir):
            if filename.startswith("batch_") and filename.endswith(".json"):
                trace_data_path = os.path.join(self.raw_data_dir, filename)
                break

        with open(trace_data_path, "r") as f:
            raw_trace_data = json.load(f)
        task_description = raw_trace_data["data"]["task_description"]
        video_url = raw_trace_data["data"]["video_url"]

        # 将video_url转换为相对路径:VIDEO_DIR拼接上video_url的后两个位置
        video_url_parts = video_url.split("/")
        relative_video_url = os.path.join(VIDEO_DIR, video_url_parts[-2], video_url_parts[-1])
        video_url = relative_video_url

        milestone_data_path = ""
        for filename in os.listdir(self.raw_data_dir):
            if filename.startswith("batch_") and filename.endswith(".md"):
                milestone_data_path = os.path.join(self.raw_data_dir, filename)
                break

        # 把md文件当时读取成类似txt文件的形式
        with open(milestone_data_path, "r") as f:
            milestones = f.read().strip().split("\n")

        trajectory = raw_trace_data["data"]["trajectory"]
        return task_description, milestones, trajectory, video_url
    
    def in_context_learning_main_task_data(self):
        """Retrieve in-context learning data"""
        # TODO: Implement the actual retrieval logic
        return "None"
    
    def in_context_learning_milestone_data(self):
        """Retrieve in-context learning milestone data"""
        # TODO: Implement the actual retrieval logic
        return "None"

    def get_img(self):
        """Capture and return the current screen image"""
        # TODO: Implement the actual image capturing logic
        return None

    def generate_roadmap(self, roadmap, task_finished):
        """Generate the roadmap string based on the current roadmap state."""
        if task_finished:
            roadmap_str = f"- [x] Project: {self.task_description}\n"
        else:
            roadmap_str = f"- [ ] Project: {self.task_description}\n"
        for milestone in roadmap:
            if milestone["finished"]:
                roadmap_str += f"    - [x] Milestone {milestone['milestone_idx']}: {milestone['milestone_name']}\n"
            else:
                roadmap_str += f"    - [ ] Milestone {milestone['milestone_idx']}: {milestone['milestone_name']}\n"
            for step in milestone["steps"]:
                if step["finished"]:
                    roadmap_str += f"        - [x] Step {step['step_idx']}: {step['action']}\n"
                else:
                    roadmap_str += f"        - [ ] Step {step['step_idx']}: {step['action']}\n"
        return roadmap_str
    
    def generate_milestone_task_data(self, teach_mode=False):
        """Generate the milestone task data."""
        new_data = []
        if teach_mode:
            instruction = milestone_task_instruction_template.format(
                self.task_description,
                self.in_context_learning_milestone_data()
            )
        else:
            instruction = milestone_task_instruction_template_no_teach.format(
                self.task_description
            )
        answer = milestone_task_answer_template.format(
            "\n".join([f"- {milestone}" for milestone in self.milestones])
        )
        new_data.append({
            "messages":[
                {"role": "system", "content": milestone_task_system_prompt_template},
                {"role": "user", "content": instruction},
                {"role": "assistant", "content": answer}
            ],
            "images": [
                self.get_img()
            ]
        })
        return new_data

    def generate_main_task_data(self, teach_mode=False):
        """Generate the main task data."""
        new_data = []
        current_milestone = ""
        # current_roadmap = f"- [ ] Project: {self.task_description}"
        roadmap = []
        task_finished = False
        for idx, step in enumerate(self.trajectory):
            if "milestone" in step.keys():
                current_milestone = step["milestone"]["milestone_name"]
                milestone_idx = step["milestone"]["idx"]
                # current_roadmap += f"\n    - [ ] Milestone {milestone_idx}: {current_milestone}\n"
                milestone_info = {
                    "milestone_idx": milestone_idx,
                    "milestone_name": current_milestone,
                    "finished": False,
                    "steps": []
                }
                roadmap.append(milestone_info)
            else:
                step_idx = step['step_idx']
                caption = step['caption']
                observation_action_before = caption['observation_action_before']
                think = caption['think']
                action = caption['action']
                expectation = caption['expectation']
                
                if "caption_prompt_input[Debug]" not in step.keys():
                    textual_action = "Wait"
                    debug_action = None
                else:
                    true_action = step['caption_prompt_input[Debug]']['action']
                    # keep textual_action string for human-readable text
                    textual_action = [true_action[1], true_action[2]]
                    textual_action = ''.join(map(str, textual_action))
                    # pass the raw debug-action-list to planner so it can extract coords
                    debug_action = true_action
                
                frame_timestamp = step['time_info']["start_time"]
                frame_path = self.img_save_dir + f"/{self.task_id}_step_{idx}_at_{frame_timestamp:.2f}s.jpg"
                self.extractor.extract_frame(frame_timestamp, save_path=frame_path)

                current_roadmap = self.generate_roadmap(roadmap, task_finished)
                roadmap[-1]["steps"].append({
                    "step_idx": step_idx,
                    "action": action,
                    "finished": True
                })
                if idx == len(self.trajectory) - 1:
                    roadmap[-1]["finished"] = True
                    task_finished = True
                else:
                    if "milestone" in self.trajectory[idx + 1].keys():
                        roadmap[-1]["finished"] = True
                next_roadmap = self.generate_roadmap(roadmap, task_finished)
                
                example = self.in_context_learning_main_task_data()

                if teach_mode:
                    instruction = main_task_instruction_template.format(
                        self.task_description,
                        current_milestone,
                        current_roadmap,
                        example
                    )
                else:
                    instruction = main_task_instruction_template_no_teach.format(
                        self.task_description,
                        current_milestone,
                        current_roadmap
                    )

                answer = main_task_answer_template.format(
                    observation_action_before,
                    think,
                    next_roadmap,
                    action,
                    textual_action
                )
                
                new_data.append({
                    "messages":[
                        {"role": "system", "content": main_task_system_prompt_template_v1},
                        {"role": "user", "content": instruction},
                        {"role": "assistant", "content": answer}
                    ],
                    "images": [
                        frame_path
                    ]
                })
                
        return new_data

    def _plan_function_calls(self, step):
        """Map the source action (string or debug-action-list) to a single function call.

        Accepts either:
        - a string (action_text), or
        - a debug action list with format [timestamp, action_str, [{"x":..,"y":..}, ...]]

        Rules:
        - Do NOT invent extra primitives (no screenshot/wait/retries).
        - If metadata provides coordinates, prefer them.
        - If action matches `DEFAULT_CLICK_ACTIONS` prefixes, map to corresponding mouse/scroll functions.
        - For unknown actions, emit `record_action` preserving the original action value.
        """

        calls = []
        if "caption_prompt_input[Debug]" not in step.keys():
            calls.append({
                    "name": "wait",
                    "arguments": None
                })
        else:
            action = step['caption_prompt_input[Debug]']['action']
            action_name = action[1]
            if ":" in action_name:
                real_action_name = action_name.split(":")[0]
                action_args = action_name.split(": ")[1]
                function_name = DEFAULT_ACTION_MAP.get(real_action_name, "error_action")
                calls.append({
                    "name": function_name,
                    "arguments": {"key": action_args}
                })
            elif action_name in ACTIONS_WITH_ONE_COORD:
                action_args = action[2][0]
                function_name = DEFAULT_ACTION_MAP.get(action_name, "error_action")
                calls.append({
                    "name": function_name,
                    "arguments": action_args
                })
            elif action_name in ACTIONS_WITH_MANY_COORDS:
                action_args = action[2]
                function_name = DEFAULT_ACTION_MAP.get(action_name, "error_action")
                calls.append({
                    "name": function_name,
                    "arguments": {"coord_list": action_args}
                })
            else:
                # raise error for unknown action
                raise ValueError(f"Unknown action format: {action}")
        return calls

    def generate_main_task_data_qwen3(self, teach_mode=False):
        """Generate main task data in Qwen3-like format: produce system/user/assistant(reasoning) and function_call messages.

        The assistant message contains a `reasoning_content` describing the chosen sequence of function calls.
        Subsequent assistant messages emit `function_call` entries following `main_task_system_prompt_template_v1` rules.
        """
        new_data = []
        current_milestone = ""
        roadmap = []
        task_finished = False
        for idx, step in enumerate(self.trajectory):
            if "milestone" in step.keys():
                current_milestone = step["milestone"]["milestone_name"]
                milestone_idx = step["milestone"]["idx"]
                milestone_info = {
                    "milestone_idx": milestone_idx,
                    "milestone_name": current_milestone,
                    "finished": False,
                    "steps": []
                }
                roadmap.append(milestone_info)
            else:
                step_idx = step['step_idx']
                caption = step['caption']
                observation_action_before = caption['observation_action_before']
                think = caption['think']
                action = caption['action']
                expectation = caption['expectation']
                try:
                    function_calls = self._plan_function_calls(step)
                except ValueError as ve:
                    # 无法识别action时跳过该step
                    print(f"    {SYMBOL_CROSS} Skipping step {step_idx} in task {self.task_id} due to error: {str(ve)}")
                    continue

                frame_timestamp = step['time_info']["start_time"]
                frame_path = self.img_save_dir + f"/{self.task_id}_step_{idx}_at_{frame_timestamp:.2f}s.jpg"
                # ensure frame extraction (idempotent in extractor)
                self.extractor.extract_frame(frame_timestamp, save_path=frame_path)

                current_roadmap = self.generate_roadmap(roadmap, task_finished)
                roadmap[-1]["steps"].append({
                    "step_idx": step_idx,
                    "action": action,
                    "finished": True
                })
                if idx == len(self.trajectory) - 1:
                    roadmap[-1]["finished"] = True
                    task_finished = True
                else:
                    if "milestone" in self.trajectory[idx + 1].keys():
                        roadmap[-1]["finished"] = True
                next_roadmap = self.generate_roadmap(roadmap, task_finished)

                example = self.in_context_learning_main_task_data()

                if teach_mode:
                    instruction = main_task_instruction_template.format(
                        self.task_description,
                        current_milestone,
                        current_roadmap,
                        example
                    )
                else:
                    instruction = main_task_instruction_template_no_teach.format(
                        self.task_description,
                        current_milestone,
                        current_roadmap
                    )

                reasoning_content = main_task_reasoning_template.format(
                    observation_action_before,
                    think,
                    next_roadmap
                )

                # create assistant message with reasoning_content (empty content)
                messages = []
                messages.append({"role": "system", "content": main_task_system_prompt_template_v1})
                messages.append({"role": "user", "content": instruction})
                messages.append({"role": "assistant", "content": "", "reasoning_content": reasoning_content})

                # append each planned call as a separate assistant function_call message
                for action in function_calls:
                    messages.append({
                        "role": "assistant",
                        "content": "",
                        "function_call": action
                    })

                new_data.append({
                    "messages": messages,
                    "images": [frame_path]
                })

        return new_data
    
    def generate_step_task_data_qwen3(self):
        """Generate step task data in Qwen3-like format."""
        new_data = []
        for idx, step in enumerate(self.trajectory):
            if "milestone" in step.keys():
                continue
            step_idx = step['step_idx']
            caption = step['caption']
            observation_action_before = caption['observation_action_before']
            think = caption['think']
            action = caption['action']
            try:
                function_calls = self._plan_function_calls(step)
            except ValueError as ve:
                # 无法识别action时跳过该step
                print(f"    {SYMBOL_CROSS} Skipping step {step_idx} in task {self.task_id} due to error: {str(ve)}")
                continue
        
            frame_timestamp = step['time_info']["start_time"]
            frame_path = self.img_save_dir + f"/{self.task_id}_step_{idx}_at_{frame_timestamp:.2f}s.jpg"

            instruction = step_task_instruction_template.format(action)
            messages = []
            messages.append({"role": "system", "content": main_task_system_prompt_template_v1})
            messages.append({"role": "user", "content": instruction})
            for action in function_calls:
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "function_call": action
                })

            new_data.append({
                "messages": messages,
                "images": [frame_path]
            })

        return new_data


class RawDataProcessor: 
    def __init__(self, raw_data_dir, save_dir, data_id="default",
                 skip_processed=True, retry_failed=False, top_num=None,
                 trace_ids=None, task_types=None):
        """ Initialize the RawDataProcessor with the directory containing raw data. """
        self.raw_data_dir = raw_data_dir
        self.save_dir = os.path.join(save_dir, data_id)
        # mode/config options
        # skip already processed tasks when True
        self.skip_processed = skip_processed
        # if True, retry previously failed tasks; otherwise skip failed tasks
        self.retry_failed = retry_failed
        # default top_num for processing (can be overridden in ProcessAllTraceData)
        self.top_num = top_num
        # optional explicit list of trace/task ids to process (takes precedence)
        self.trace_ids = trace_ids
        # optional filter: list of substrings; only task ids containing any of these will be processed
        self.task_types = task_types
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
        self.img_save_dir = os.path.join(self.save_dir, "images")
        if not os.path.exists(self.img_save_dir):
            os.makedirs(self.img_save_dir)
        # progress file for checkpoint/resume
        self.progress_path = os.path.join(self.save_dir, "progress.json")
        if os.path.exists(self.progress_path):
            try:
                with open(self.progress_path, "r") as f:
                    prog = json.load(f)
                    self.processed_tasks = set(prog.get("processed_tasks", []))
                    self.failed_tasks = set(prog.get("failed_tasks", []))
            except Exception:
                self.processed_tasks = set()
                self.failed_tasks = set()
        else:
            self.processed_tasks = set()
            self.failed_tasks = set()

    def _append_and_save_json(self, path, items):
        """Append items to a JSON array file (create if missing)."""
        existing = []
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        existing.extend(items)
        with open(path, "w") as f:
            json.dump(existing, f, indent=4, ensure_ascii=False)

    def _save_progress(self):
        try:
            with open(self.progress_path, "w") as f:
                json.dump({"processed_tasks": list(self.processed_tasks), "failed_tasks": list(self.failed_tasks)}, f, indent=2)
        except Exception:
            pass

    def _append_and_save_error(self, task_id, error_msg):
        """Append an error record to errors.json for later inspection."""
        errors_path = os.path.join(self.save_dir, "errors.json")
        record = {"task_id": task_id, "error": error_msg}
        existing = []
        if os.path.exists(errors_path):
            try:
                with open(errors_path, "r") as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        existing.append(record)
        try:
            with open(errors_path, "w") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_task_id_list(self, top_num=None):
        """ Get the list of task IDs from the raw data directory. """
        task_id_list = os.listdir(self.raw_data_dir)
        # sort task_id_list
        task_id_list.sort()
        if top_num is not None:
            task_id_list = task_id_list[:top_num]
        return task_id_list


    def ProcessAllTraceData(self, top_num=None):
        """ Process all trace data in the specified directory. """
        # Build base list: explicit trace_ids take precedence
        if self.trace_ids is not None:
            task_id_list = list(self.trace_ids)
        else:
            # choose top_num passed to method first, then one from config
            use_top = top_num if top_num is not None else self.top_num
            task_id_list = self.get_task_id_list(use_top)

        # filter by task_types if provided
        if self.task_types:
            filtered = []
            for tid in task_id_list:
                for tt in self.task_types:
                    if tt in tid:
                        filtered.append(tid)
                        break
            task_id_list = filtered

        all_milestone_data = []
        # all_main_task_data = []
        all_main_task_data_qwen3 = []
        all_step_task_data_qwen3 = []

        for task_id in task_id_list:
            # skip already processed or previously failed tasks (checkpoint/resume)
            if self.skip_processed and task_id in getattr(self, "processed_tasks", set()):
                print(f"{SYMBOL_ARROW} Skipping already processed task: {task_id}")
                continue
            if (not self.retry_failed) and task_id in getattr(self, "failed_tasks", set()):
                print(f"{SYMBOL_ARROW} Skipping previously failed task: {task_id}")
                continue

            # process each task with error handling so anomalies are recorded and skipped
            print(f"{SYMBOL_INFO} Processing task: {task_id}")
            try:
                trace_data_dir = f"{self.raw_data_dir}/{task_id}/"
                processor = RawTraceProcessor(trace_data_dir, task_id, self.img_save_dir)

                print(f"    {SYMBOL_INFO} Generateing Milestone data...")
                milestone_data = processor.generate_milestone_task_data(teach_mode=False)
                all_milestone_data.extend(milestone_data)
                milestone_save_path = os.path.join(self.save_dir, "milestone_task_data.json")
                self._append_and_save_json(milestone_save_path, milestone_data)
                print(f"    ✅ Milestone data saved to {milestone_save_path}")

                print(f"    {SYMBOL_INFO} Generateing Main Task data (Qwen3 format)...")
                main_task_data_qwen3 = processor.generate_main_task_data_qwen3(teach_mode=False)
                all_main_task_data_qwen3.extend(main_task_data_qwen3)
                main_task_qwen3_save_path = os.path.join(self.save_dir, "main_task_data_qwen3.json")
                self._append_and_save_json(main_task_qwen3_save_path, main_task_data_qwen3)
                print(f"    ✅ Main Task data (Qwen3 format) saved to {main_task_qwen3_save_path}")

                print(f"    {SYMBOL_INFO} Generateing Step Task data (Qwen3 format)...")
                step_task_data_qwen3 = processor.generate_step_task_data_qwen3()
                all_step_task_data_qwen3.extend(step_task_data_qwen3)
                step_task_qwen3_save_path = os.path.join(self.save_dir, "step_task_data_qwen3.json")
                self._append_and_save_json(step_task_qwen3_save_path, step_task_data_qwen3)
                print(f"    ✅ Step Task data (Qwen3 format) saved to {step_task_qwen3_save_path}")

                # mark task as processed and persist progress
                self.processed_tasks.add(task_id)
                self._save_progress()
            except Exception as e:
                error_msg = str(e)
                print(f"    {SYMBOL_CROSS} Error processing task {task_id}: {error_msg}")
                self._append_and_save_error(task_id, error_msg)
                # mark task as failed and persist progress
                self.failed_tasks.add(task_id)
                self._save_progress()
                continue


        print(f"✅ Processed data saved to {self.save_dir}")
    


    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process trace hierarchy data into dataset JSONs with checkpointing.")
    parser.add_argument("--raw-data-dir", default="/data/lhx/LLaMA-Factory/data/temp_batch/batch_partial_result_v0/",
                        help="Root directory containing raw trace task folders")
    parser.add_argument("--save-dir", default="/data/lhx/LLaMA-Factory/data/demo/data_generator/data/",
                        help="Directory to write processed data and progress files")
    parser.add_argument("--data-id", default="test_new", help="Subdirectory name under save-dir to store outputs")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--skip-processed", dest="skip_processed", action="store_true",
                       help="Skip tasks already recorded as processed (default)")
    group.add_argument("--no-skip-processed", dest="skip_processed", action="store_false",
                       help="Do not skip tasks recorded as processed")
    parser.set_defaults(skip_processed=True)

    parser.add_argument("--retry-failed", action="store_true", help="Retry tasks recorded as failed")
    parser.add_argument("--top-num", type=int, default=None,
                        help="Limit to first N tasks from the raw data directory")
    parser.add_argument("--trace-ids", nargs="+", default=None,
                        help="Explicit list of trace/task ids to process (space-separated)")
    parser.add_argument("--task-types", nargs="+", default=None,
                        help="Filter task ids by these substrings (space-separated)")

    args = parser.parse_args()

    processor = RawDataProcessor(
        args.raw_data_dir,
        args.save_dir,
        args.data_id,
        skip_processed=args.skip_processed,
        retry_failed=args.retry_failed,
        top_num=args.top_num,
        trace_ids=args.trace_ids,
        task_types=args.task_types,
    )

    # call with no override (constructor top_num used), but allow override if desired
    processor.ProcessAllTraceData()
        
        
        
        