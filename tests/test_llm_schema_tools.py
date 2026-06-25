import json
from pathlib import Path

from work.llm_wiki_solver.llm_client import FakeLLMClient, LLMClient, LLMConfig
from work.llm_wiki_solver.llm_pipeline import (
    AnswerComposer,
    EvidenceCard,
    QuestionPlanner,
    ComplexUnderstandingPipeline,
    answer_draft_schema,
    repair_plan_schema,
    query_plan_schema,
    RepairPlanner,
)
from work.llm_wiki_solver.models import Question
from work.llm_wiki_solver.permissions import PermissionGuard


def test_question_planner_passes_strict_query_plan_schema():
    client = FakeLLMClient(
        [
            {
                "intent": "knowledge_query",
                "answer_format": "datas",
                "subqueries": ["计费业务"],
                "filters": {},
                "needs_repair": False,
                "needs_execution": False,
                "confidence": 0.9,
            }
        ]
    )

    QuestionPlanner(client).plan(
        Question(id="group-1-1", title="计费业务涉及哪些文件", level="困难"),
        {"datas": []},
    )

    assert client.schemas[0] == query_plan_schema()


def test_answer_composer_passes_strict_answer_draft_schema():
    client = FakeLLMClient(
        [
            {
                "answer": {"datas": ["docs/00_业务总结/计费业务总结.md"]},
                "evidence_sources": ["docs/00_业务总结/计费业务总结.md"],
                "confidence": 0.8,
                "warnings": [],
            }
        ]
    )

    AnswerComposer(client).compose(
        Question(id="group-1-1", title="计费业务涉及哪些文件", level="困难"),
        plan=QuestionPlanner(
            FakeLLMClient(
                [
                    {
                        "intent": "knowledge_query",
                        "answer_format": "datas",
                        "subqueries": ["计费业务"],
                        "filters": {},
                        "needs_repair": False,
                        "needs_execution": False,
                        "confidence": 0.9,
                    }
                ]
            )
        ).plan(Question(id="group-1-1", title="计费业务涉及哪些文件", level="困难"), {"datas": []}),
        cards=[
            EvidenceCard(
                source="docs/00_业务总结/计费业务总结.md",
                evidence_type="chunk",
                text="计费业务包含套餐、账单、折扣三个核心模块。",
                score=1.0,
            )
        ],
    )

    assert client.schemas[0] == answer_draft_schema()


def test_repair_planner_passes_strict_repair_plan_schema():
    client = FakeLLMClient(
        [
            {
                "intent": "repair",
                "answer_format": "repair",
                "subqueries": ["张三"],
                "filters": {},
                "needs_repair": True,
                "needs_execution": False,
                "confidence": 0.91,
            },
            {
                "source": "docs/05_需求设计/产品规则详解.md",
                "target": "output/fixed/05_需求设计/产品规则详解.md",
                "operations": [
                    {
                        "op": "replace_text",
                        "old": "todo: 补充产品报价字段",
                        "new": "todo: 补充产品报价字段, status: done",
                    }
                ],
                "confidence": 0.82,
            },
        ]
    )

    question = Question(id="group-1-5", title="修复责任人为张三的TODO事项", level="困难")
    plan = QuestionPlanner(client).plan(question, {"source": "docs/05_需求设计/产品规则详解.md", "target": "output/fixed/05_需求设计/产品规则详解.md"})

    RepairPlanner(client).plan(
        question,
        plan,
        [
            EvidenceCard(
                source="docs/05_需求设计/产品规则详解.md",
                evidence_type="fact",
                text="todo: 补充产品报价字段, to: 张三,end_date: 20251231",
                score=1.0,
            )
        ],
        {"source": "docs/05_需求设计/产品规则详解.md", "target": "output/fixed/05_需求设计/产品规则详解.md"},
    )

    assert client.schemas[1] == repair_plan_schema()


def test_pipeline_uses_repair_planner_for_repair_intent(tmp_path):
    root = tmp_path / "llm-wiki"
    docs = root / "docs"
    docs.mkdir(parents=True)
    (root / "Permission.json").write_text("{}", encoding="utf-8")
    (docs / "05_需求设计").mkdir(parents=True)
    (docs / "05_需求设计" / "产品规则详解.md").write_text(
        "<!-- todo: 补充产品报价字段, to: 张三,end_date: 20251231 -->",
        encoding="utf-8",
    )

    client = FakeLLMClient(
        [
            {
                "intent": "repair",
                "answer_format": "repair",
                "subqueries": ["张三", "产品规则详解"],
                "filters": {},
                "needs_repair": True,
                "needs_execution": False,
                "confidence": 0.95,
            },
            {
                "source": "docs/05_需求设计/产品规则详解.md",
                "target": "output/fixed/05_需求设计/产品规则详解.md",
                "operations": [{"op": "copy_file"}],
                "confidence": 0.8,
            },
        ]
    )

    pipeline = ComplexUnderstandingPipeline(
        records=[],
        permission_guard=PermissionGuard({}),
        llm_client=client,
        root=root,
    )

    result = pipeline.solve(
        Question(id="group-1-5", title="修复责任人为张三的TODO事项", level="困难"),
        fallback_answer={
            "source": "docs/05_需求设计/产品规则详解.md",
            "target": "output/fixed/05_需求设计/产品规则详解.md",
        },
    )

    assert result.answer == {
        "source": "docs/05_需求设计/产品规则详解.md",
        "target": "output/fixed/05_需求设计/产品规则详解.md",
    }
    assert "repair_plan" in result.trace
    assert client.schemas[1] == repair_plan_schema()


def test_fake_llm_rejects_response_missing_required_schema_fields():
    client = FakeLLMClient([{"intent": "knowledge_query"}], validate_schema=True)

    try:
        QuestionPlanner(client).plan(
            Question(id="group-1-1", title="计费业务涉及哪些文件", level="困难"),
            {"datas": []},
        )
    except Exception as exc:
        assert "schema" in str(exc).lower() or "required" in str(exc).lower()
    else:
        raise AssertionError("schema validation should reject incomplete query plan")


def test_llm_client_tool_payload_uses_function_call_shape(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "submit_query_plan",
                                            "arguments": json.dumps(
                                                {
                                                    "intent": "knowledge_query",
                                                    "answer_format": "datas",
                                                    "subqueries": ["计费业务"],
                                                    "filters": {},
                                                    "needs_repair": False,
                                                    "needs_execution": False,
                                                    "confidence": 0.9,
                                                },
                                                ensure_ascii=False,
                                            ),
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                },
                ensure_ascii=False,
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = LLMClient(
        LLMConfig(
            endpoint="https://model.example/v1/chat",
            model_name="glm-test",
            api_key="secret",
            tool_calling=True,
        )
    )

    result = client.complete_json("plan", query_plan_schema())

    assert captured["payload"]["tools"][0]["function"]["name"] == "submit_structured_response"
    assert captured["payload"]["tool_choice"]["function"]["name"] == "submit_structured_response"
    assert result["intent"] == "knowledge_query"
