import json

from utxolab.cli import main
from utxolab.demo import run_scenario


def test_demo_trace_matches_expectations(tmp_path):
    lines = []
    res = run_scenario(str(tmp_path), emit=lines.append)
    recs = res["records"]
    assert [r["result"] for r in recs].count("ACCEPTED") == 2
    codes = [r["code"] for r in recs if r["result"] == "REJECTED"]
    assert codes == ["duplicate_transaction", "input_not_found", "duplicate_input", "input_already_spent",
                     "bad_signature", "pubkey_hash_mismatch", "bad_output_value", "value_overflow",
                     "outputs_exceed_inputs", "bad_witness"]
    assert all(r["state_unchanged"] for r in recs if r["result"] == "REJECTED")
    assert len(res["snapshots"]) == 3


def test_demo_is_deterministic():
    a, b = [], []
    run_scenario(emit=a.append)
    run_scenario(emit=b.append)
    assert a == b


def test_cli_check_and_apply(tmp_path, capsys):
    res = run_scenario(str(tmp_path), emit=lambda _m: None)
    genesis = sorted(tmp_path.glob("00_*.json"))[0]
    txfile = tmp_path / "tx.json"
    txfile.write_text(json.dumps(res["pay_tx"].to_obj()))
    assert main(["check-tx", "--state", str(genesis), "--tx", str(txfile)]) == 0
    assert "fee: 2" in capsys.readouterr().out
    out = tmp_path / "after.json"
    assert main(["apply-tx", "--state", str(genesis), "--tx", str(txfile), "--out", str(out)]) == 0
    assert main(["apply-tx", "--state", str(out), "--tx", str(txfile)]) == 1      # replay
    assert "duplicate_transaction" in capsys.readouterr().err
    assert main(["inspect", str(out)]) == 0
