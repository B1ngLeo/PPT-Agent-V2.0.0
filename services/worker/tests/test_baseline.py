from instant_ppt_worker.settings import WorkerContract


def test_worker_contract_is_versioned_and_immutable() -> None:
    contract = WorkerContract()
    assert contract.schema_version == 1
    assert contract.adapter_name == "ppt-master-engine-adapter"
    assert contract.engine_version.startswith("ppt-master@v4.7.0")
