from work.llm_wiki_solver.permissions import PermissionGuard


def test_permission_guard_blocks_denied_commands_files_and_dirs():
    guard = PermissionGuard(
        {
            "dir": {"deny": ["/etc", "*/secret"]},
            "command": {"deny": ["Remove-Item", "del", "rm*"]},
            "file": {"deny": ["hadoop.env", "spark-*.env"]},
        }
    )

    assert guard.is_denied_command("rm -rf docs/tmp")
    assert guard.is_denied_command("Remove-Item docs/tmp")
    assert guard.is_denied_command("删除docs/tmp/test.md")
    assert not guard.is_denied_path("docs/99_mock_system_dir/etc/passwd", operation="read")
    assert guard.is_denied_path("docs/99_mock_system_dir/etc/passwd", operation="write")
    assert not guard.is_denied_path("docs/ops/secret/config.md", operation="read")
    assert guard.is_denied_path("docs/ops/secret/config.md", operation="write")
    assert guard.is_denied_path("docs/a/b/hadoop.env", operation="read")
    assert guard.is_denied_path("docs/a/b/hadoop.env", operation="write")
    assert guard.is_denied_path("docs/a/b/spark-prod.env", operation="read")
    assert guard.is_denied_path("docs/a/b/spark-prod.env", operation="write")


def test_permission_guard_allows_non_matching_paths_and_commands():
    guard = PermissionGuard(
        {
            "dir": {"deny": ["/etc"]},
            "command": {"deny": ["del"]},
            "file": {"deny": ["spark-*.env"]},
        }
    )

    assert not guard.is_denied_command("git status")
    assert not guard.is_denied_path("docs/02_环境信息/op_user.env", operation="read")
    assert not guard.is_denied_path("docs/config/spark_notes.md", operation="read")
