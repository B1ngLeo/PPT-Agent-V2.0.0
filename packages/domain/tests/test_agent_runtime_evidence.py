from alembic.config import Config
from alembic.script import ScriptDirectory
from instant_ppt_domain.models import (
    Base,
    WorkflowAgentToolCall,
    WorkflowAgentTurn,
)


def test_agent_turn_and_tool_tables_have_tenant_scoped_audit_constraints() -> None:
    turn = WorkflowAgentTurn.__table__
    tool = WorkflowAgentToolCall.__table__

    assert turn.name == "workflow_agent_turns"
    assert tool.name == "workflow_agent_tool_calls"
    assert turn.c.decision.type.__class__.__name__ == "JSONB"
    assert tool.c.observation.type.__class__.__name__ == "JSONB"
    assert tool.c.agent_turn_id.nullable is False
    assert {constraint.name for constraint in turn.constraints} >= {
        "uq_workflow_agent_turns_id_org",
        "uq_workflow_agent_turns_run_sequence",
        "ck_workflow_agent_turns_valid_role",
    }
    assert {constraint.name for constraint in tool.constraints} >= {
        "fk_workflow_agent_tool_calls_turn_org",
        "ck_workflow_agent_tool_calls_author_attempt_bounded",
    }
    assert "workflow_agent_turns" in Base.metadata.tables
    assert "workflow_agent_tool_calls" in Base.metadata.tables


def test_issue003_authoring_profile_migration_is_the_single_head() -> None:
    config = Config("packages/domain/src/instant_ppt_domain/alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert script.get_current_head() == "c82d5f1a7b04"
    revision = script.get_revision("c82d5f1a7b04")
    assert revision is not None
    assert revision.down_revision == "b71c4e2f9a03"
