import json
import sys
import pathlib
import asyncio

from typing             import Any
from typing             import Optional
from typing             import Dict
from typing             import List
from langchain.messages import AIMessageChunk

class JSONFormatHelper:
    @staticmethod
    def render_inline(value: Any) -> Optional[str]:
        # 한 줄로 표현 가능하면 그 문자열을, 여러 줄로 펼쳐야 하면 None을 반환한다.
        # 인라인 가능 조건 : 스칼라 / 빈 컨테이너 / 항목 1개이면서 그 항목도 인라인 가능.
        if isinstance(value, dict):
            if len(value) == 0:
                return "{}"
            if len(value) == 1:
                only_key = next(iter(value))
                inner_string = JSONFormatHelper.render_inline(value[only_key])
                if inner_string is None:
                    return None
                return "{" + json.dumps(only_key, ensure_ascii=False) + " : " + inner_string + "}"
            return None
        if isinstance(value, list):
            if len(value) == 0:
                return "[]"
            if len(value) == 1:
                inner_string = JSONFormatHelper.render_inline(value[0])
                if inner_string is None:
                    return None
                return "[" + inner_string + "]"
            return None
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def render(value: Any, indent_count: int) -> str:
        # 인라인 가능하면 한 줄로, 아니면 indent_count(닫는 괄호의 열 위치)를 기준으로 여러 줄로 펼친다.
        inline_string = JSONFormatHelper.render_inline(value)
        if inline_string is not None:
            return inline_string
        child_indent = " " * (indent_count + 4)
        close_indent = " " * indent_count
        if isinstance(value, dict):
            key_list = list(value.keys())
            maximum_key_length = max(len(json.dumps(key, ensure_ascii=False)) for key in key_list)  # dict 단위 한 열 정렬
            line_list = []
            for key in key_list:
                padded_key = json.dumps(key, ensure_ascii=False).ljust(maximum_key_length)
                child_string = JSONFormatHelper.render(value[key], indent_count + 4)
                line_list.append(child_indent + padded_key + " : " + child_string)
            return "{\n" + ",\n".join(line_list) + "\n" + close_indent + "}"
        # list (2개 이상 또는 항목이 펼쳐지는 경우)
        line_list = []
        for item in value:
            child_string = JSONFormatHelper.render(item, indent_count + 4)
            line_list.append(child_indent + child_string)
        return "[\n" + ",\n".join(line_list) + "\n" + close_indent + "]"


class MessageDictionaryHelper:
    @staticmethod
    def merge_message_dictionary(base_message_dictionary: Dict[str, Any],
                                 additional_message_dictionary: Dict[str, Any]) -> Dict[str, Any]:
        if base_message_dictionary["type"] == "AIMessageChunk" and additional_message_dictionary[
            "type"] == "AIMessageChunk":
            base_ai_message_chunk = AIMessageChunk(**base_message_dictionary)
            additional_ai_message_chunk = AIMessageChunk(**additional_message_dictionary)
            merged_ai_message_chunk = base_ai_message_chunk + additional_ai_message_chunk
            return merged_ai_message_chunk.model_dump()
        return additional_message_dictionary


class TaskMessageFormatHelper:
    @staticmethod
    def extract_content_text(content: Any) -> Optional[str]:
        if isinstance(content, str):
            return content if content else None
        if not isinstance(content, list):
            return None
        content_text_list: List[str] = []
        for content_item in content:
            if isinstance(content_item, str):
                if content_item:
                    content_text_list.append(content_item)
                continue
            if isinstance(content_item, dict):
                text = content_item.get("text")
                if isinstance(text, str) and text:
                    content_text_list.append(text)
        if not content_text_list:
            return None
        return "".join(content_text_list)

    @staticmethod
    def format_task_message(message_dictionary: Dict[str, Any]) -> str:
        if message_dictionary is None:
            return ""
        type = message_dictionary["type"]
        if type == "AIMessageChunk":
            content = message_dictionary["content"]
            if content:
                content_text = TaskMessageFormatHelper.extract_content_text(content)
                return content_text
            else:
                tool_calls = message_dictionary["tool_calls"]
                if tool_calls and len(tool_calls) > 0:
                    tool_calls_message = ""
                    for tool_call in tool_calls:
                        tool_call_name = tool_call["name"]
                        if tool_call_name == "task" and "args" in tool_call and "subagent_type" in tool_call["args"]:
                            subagent_type = tool_call["args"]["subagent_type"]
                            tool_calls_message += f"[CALLING SUBAGENT : {subagent_type}]"
                        else:
                            tool_calls_message += f"[CALLING TOOL : {tool_call_name}]"
                    return tool_calls_message
                else:
                    return ""
        elif type == "tool":
            content = message_dictionary["content"]
            content_text = TaskMessageFormatHelper.extract_content_text(content)
            return content_text


def get_namespace_string(namespace_list: List[str]) -> str:
    return "|".join(namespace_list)


def get_owner_task_id(langgraph_checkpoint_ns: str) -> str:
    segment_list = langgraph_checkpoint_ns.split("|")
    owner_node_name, _, owner_task_id = segment_list[-1].partition(":")
    return owner_task_id


async def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    source_file_path = "source_stream.jsonl"
    source_path = pathlib.Path(source_file_path)
    if not source_path.is_file():
        print(f"SOURCE FILE NOT FOUND : {source_file_path}")
        exit()
    task_dictionary: Dict[str, Dict[str, Any]] = {}
    sequence = 1
    with open(source_path, "r", encoding="utf-8") as source_text_io_wrapper:
        while True:
            source_text = source_text_io_wrapper.readline().strip()
            if not source_text:
                break
            chunk_dictionary = json.loads(source_text)
            chunk_type = chunk_dictionary["type"]
            namespace_list = chunk_dictionary["ns"]
            namespace_string = get_namespace_string(namespace_list)
            data_dictionary = chunk_dictionary["data"]
            if chunk_type == "messages":
                message_dictionary = data_dictionary["message"]
                metadata_dictionary = data_dictionary["metadata"]
                langgraph_checkpoint_ns = metadata_dictionary["langgraph_checkpoint_ns"]
                owner_task_id = get_owner_task_id(langgraph_checkpoint_ns)
                if owner_task_id in task_dictionary:
                    if task_dictionary[owner_task_id]["message"]:
                        task_dictionary[owner_task_id]["message"] = MessageDictionaryHelper.merge_message_dictionary(
                            task_dictionary[owner_task_id]["message"], message_dictionary)
                    else:
                        task_dictionary[owner_task_id]["message"] = message_dictionary
            if chunk_type == "tasks":
                chunk_dictionary["sequence"] = sequence
                task_id = chunk_dictionary["data"]["id"]
                task_name = chunk_dictionary["data"]["name"]
                if task_id not in task_dictionary:
                    task_dictionary[task_id] = {
                        "sequence": sequence,
                        "id": task_id,
                        "name": task_name,
                        "namespace": namespace_string,
                        "agent_type": "MAIN AGENT" if not namespace_string else "SUBAGENT",
                        "agent_name": chunk_dictionary["data"]["metadata"]["lc_agent_name"],
                        "chunk_list": [chunk_dictionary],
                        "message": None,
                        "status": "RUNNING"
                    }
                else:
                    task_dictionary[task_id]["chunk_list"].append(chunk_dictionary)
                    if chunk_dictionary["data"]["error"] is None:
                        task_dictionary[task_id]["status"] = "COMPLETED"
                    else:
                        task_dictionary[task_id]["status"] = "FAILED"
                sequence += 1
    print("-" * 50)
    task_tuple_list = sorted(task_dictionary.items(), key=lambda task_tuple: task_tuple[1]["sequence"])
    for task_id, task_info in task_tuple_list:
        print(f"TASK ID         : {task_id}")
        print(f"TASK AGENT TYPE : {task_info['agent_type']}")
        print(f"TASK AGENT NAME : {task_info['agent_name']}")
        print(f"TASK NAME       : {task_info['name']}")
        task_message = TaskMessageFormatHelper.format_task_message(task_info["message"])
        print(f"TASK MESSAGE    : \033[32m{task_message}\033[0m")
        print(f"TASK STATUS     : {task_info['status']}")
        for chunk_dictionary in task_info["chunk_list"]:
            print(f"  CHUNK SEQUENCE : {chunk_dictionary['sequence']}")
            print(f"  CHUNK TYPE     : {chunk_dictionary['type']}")
        print("-" * 50)


if __name__ == "__main__":
    asyncio.run(main())