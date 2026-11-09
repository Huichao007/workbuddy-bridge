# -*- coding: utf-8 -*-
"""Unit tests for the protocol layer.

These run without WorkBuddy installed, without a named pipe and without network
access, which is the whole point: the bridge's most fragile logic is the
translation between streaming protocols, and it must be verifiable in CI.

    python -m unittest discover -s tests -v
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import responses_api  # noqa: E402
import translate  # noqa: E402


def chunk(content=None, role=None, tools=None, finish=None, idx=0,
          usage=None, model="test-model"):
    delta = {}
    if role:
        delta["role"] = role
    if content is not None:
        delta["content"] = content
    if tools:
        delta["tool_calls"] = tools
    out = {"id": "chatcmpl-1", "object": "chat.completion.chunk",
           "model": model, "choices": [{"index": idx, "delta": delta}]}
    if finish:
        out["choices"][0]["finish_reason"] = finish
    if usage:
        out["usage"] = usage
    return out


class TestAggregate(unittest.TestCase):
    def test_plain_text_is_concatenated(self):
        frames = [chunk(role="assistant"),
                  chunk("你"), chunk("好"), chunk(finish="stop")]
        out = translate.aggregate(frames)
        self.assertEqual(out["choices"][0]["message"]["content"], "你好")
        self.assertEqual(out["choices"][0]["message"]["role"], "assistant")
        self.assertEqual(out["choices"][0]["finish_reason"], "stop")
        self.assertEqual(out["object"], "chat.completion")

    def test_tool_call_fragments_are_glued_back_together(self):
        """The failure this guards: a model streams the arguments in pieces and
        we hand the client half a JSON object, so Agent mode breaks."""
        frames = [
            chunk(role="assistant"),
            chunk(tools=[{"index": 0, "id": "call_abc", "type": "function",
                          "function": {"name": "read_file", "arguments": ""}}]),
            chunk(tools=[{"index": 0, "function": {"arguments": '{"pa'}}]),
            chunk(tools=[{"index": 0, "function": {"arguments": 'th": "a'}}]),
            chunk(tools=[{"index": 0, "function": {"arguments": '.py"}'}}]),
            chunk(finish="tool_calls"),
        ]
        out = translate.aggregate(frames)
        calls = out["choices"][0]["message"]["tool_calls"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["id"], "call_abc")
        self.assertEqual(calls[0]["function"]["name"], "read_file")
        self.assertEqual(json.loads(calls[0]["function"]["arguments"]),
                         {"path": "a.py"})

    def test_parallel_tool_calls_stay_separate(self):
        frames = [
            chunk(role="assistant"),
            chunk(tools=[{"index": 0, "id": "call_a",
                          "function": {"name": "f", "arguments": "{\"a\":1}"}}]),
            chunk(tools=[{"index": 1, "id": "call_b",
                          "function": {"name": "g", "arguments": "{\"b\":2}"}}]),
            chunk(finish="tool_calls"),
        ]
        calls = translate.aggregate(frames)["choices"][0]["message"]["tool_calls"]
        self.assertEqual([c["id"] for c in calls], ["call_a", "call_b"])
        self.assertEqual(calls[1]["function"]["name"], "g")

    def test_missing_usage_becomes_zeroed(self):
        out = translate.aggregate([chunk("hi")])
        self.assertEqual(out["usage"],
                         {"prompt_tokens": 0, "completion_tokens": 0,
                          "total_tokens": 0})

    def test_usage_is_passed_through(self):
        frames = [chunk("hi"),
                  chunk(usage={"prompt_tokens": 5, "completion_tokens": 2,
                               "total_tokens": 7})]
        self.assertEqual(translate.aggregate(frames)["usage"]["total_tokens"], 7)

    def test_empty_frames_do_not_crash(self):
        out = translate.aggregate([])
        self.assertEqual(out["choices"], [])
        self.assertEqual(out["usage"]["total_tokens"], 0)


class TestSse(unittest.TestCase):
    def test_round_trip(self):
        frames = [chunk("hello"), chunk(" world", finish="stop")]
        text = translate.sse_text(frames)
        self.assertTrue(text.endswith("data: [DONE]\n\n"))
        self.assertEqual(translate.parse_sse(text), frames)

    def test_parse_ignores_noise(self):
        body = (": keepalive\n"
                "data: \n"
                "data: [DONE]\n"
                "data: {\"a\": 1}\n"
                "random noise\n"
                "data: {broken json\n")
        frames = translate.parse_sse(body)
        self.assertEqual(frames, [{"a": 1}])
        self.assertTrue(translate.has_stream_noise(body))

    def test_clean_body_has_no_noise(self):
        self.assertFalse(translate.has_stream_noise(
            translate.sse_text([chunk("x")])))


class TestResponsesTranslation(unittest.TestCase):
    def test_instructions_become_system_message(self):
        body = responses_api.to_chat_request({
            "model": "m",
            "instructions": "be brief",
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": "hi"}]}],
        })
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(body["messages"][-1]["content"], "hi")
        self.assertTrue(body["stream"], "gateway only speaks streaming")

    def test_responses_tools_become_chat_tools(self):
        body = responses_api.to_chat_request({
            "model": "m",
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": "go"}]}],
            "tools": [{"type": "function", "name": "do_it",
                       "description": "d",
                       "parameters": {"type": "object"}}],
        })
        self.assertEqual(body["tools"][0]["type"], "function")
        self.assertEqual(body["tools"][0]["function"]["name"], "do_it")

    def test_reasoning_effort_is_carried_over(self):
        body = responses_api.to_chat_request({
            "model": "m", "input": [{"role": "user", "content": "x"}],
            "reasoning": {"effort": "high"},
        })
        self.assertEqual(body.get("reasoning_effort"), "high")

    def test_non_streaming_response_is_complete(self):
        frames = [chunk(role="assistant"), chunk("done", finish="stop")]
        out = responses_api.json_from_frames(frames, "m")
        self.assertEqual(out["object"], "response")
        self.assertEqual(out["status"], "completed")
        text = "".join(
            p.get("text", "")
            for item in out.get("output") or []
            if item.get("type") == "message"
            for p in item.get("content") or [])
        self.assertEqual(text, "done")

    def test_sse_event_sequence(self):
        text = responses_api.sse_from_frames(
            [chunk(role="assistant"), chunk("ok", finish="stop")], "m")
        kinds = [l[7:] for l in text.splitlines() if l.startswith("event: ")]
        self.assertEqual(kinds[0], "response.created")
        self.assertIn("response.output_item.added", kinds)
        self.assertEqual(kinds[-1], "response.completed")
        self.assertIn("response.output_text.delta", kinds)


if __name__ == "__main__":
    unittest.main(verbosity=2)
