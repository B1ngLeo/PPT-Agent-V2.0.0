from instant_ppt_worker.tasks import process_generation_job_task, process_planning_job_task


def test_generation_task_outlives_workflow_hard_timeout() -> None:
    assert process_generation_job_task.soft_time_limit > 7500
    assert (
        process_generation_job_task.time_limit
        > process_generation_job_task.soft_time_limit
    )


def test_planning_task_outlives_one_structured_provider_attempt() -> None:
    assert process_planning_job_task.soft_time_limit >= 3900
    assert process_planning_job_task.time_limit > process_planning_job_task.soft_time_limit
