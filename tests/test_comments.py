from work.llm_wiki_solver.comments import extract_comment_records, parse_structured_todo


def test_parse_structured_todo_accepts_mixed_punctuation_and_spacing():
    record = parse_structured_todo(
        "TODO：补充产品报价字段,to: 李四，end_date：20251231",
        source="docs/05_需求设计/产品规则.md",
        location="line:7",
        kind="code",
    )

    assert record is not None
    assert record.text == "todo: 补充产品报价字段, to: 李四, end_date: 20251231"
    assert record.assignee == "李四"
    assert record.end_date == "20251231"
    assert record.kind == "code"


def test_extract_comment_records_finds_structured_and_free_code_comments():
    text = """
# TODO: 待实现接口,to:王五,end_date:20251015
value = 1
/* 需要重构sql逻辑 */
"""

    records = extract_comment_records(
        text,
        source="docs/01_技术总结/demo.py",
        suffix="py",
    )

    assert [record.assignee for record in records[:1]] == ["王五"]
    assert records[1].text == "需要重构sql逻辑"
    assert records[1].kind == "free"


def test_extract_comment_records_finds_js_line_comments():
    records = extract_comment_records(
        "// TODO: 优化异常捕获,to:赵六,end_date:20250920\n",
        source="docs/01_技术总结/demo.js",
        suffix="js",
    )

    assert [record.assignee for record in records] == ["赵六"]


def test_extract_comment_records_does_not_treat_markdown_headings_as_comments():
    text = """# 产品规则详解

正文。

<!-- todo: 补充字段,to:张三,end_date:20251231 -->
"""

    records = extract_comment_records(
        text,
        source="docs/05_需求设计/产品规则详解.md",
        suffix="md",
    )

    assert [record.text for record in records] == [
        "todo: 补充字段, to: 张三, end_date: 20251231"
    ]


def test_parse_structured_todo_accepts_spaced_date_digits():
    record = parse_structured_todo(
        "todo: 补充验收说明, to: 张三,end_date: 2025 12 31",
        "docs/a.md",
        "line:1",
    )

    assert record is not None
    assert record.text == "todo: 补充验收说明, to: 张三, end_date: 20251231"
    assert record.end_date == "20251231"
