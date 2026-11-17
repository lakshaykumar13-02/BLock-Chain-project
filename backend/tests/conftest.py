import os
import shutil
import tempfile
import hashlib
import time
import pytest
from pathlib import Path

# Ensure tests strictly target chainvault_test
os.environ["MONGO_DB_NAME"] = "chainvault_test"

@pytest.fixture(autouse=True)
def enforce_test_database_isolation():
    """Guarantee that tests never target the development database."""
    assert os.getenv("MONGO_DB_NAME") == "chainvault_test", (
        "CRITICAL SAFETY VIOLATION: Test suite executed with non-test database! "
        f"Expected 'chainvault_test', got '{os.getenv('MONGO_DB_NAME')}'."
    )
    yield


@pytest.fixture(autouse=True)
def deterministic_blockchain_rpc_fixture(monkeypatch):
    """
    Ensures deterministic, reliable blockchain testing even when local Hardhat RPC node
    on port 8545 is not manually running.
    Intercepts app.services.blockchain._rpc_call with an in-process JSON-RPC simulation
    that executes against CHAIN_EVIDENCE_STORE and CHAIN_CUSTODY_LOGS.
    Tests that explicitly test RPC down/error by monkeypatching query_contract_evidence
    or _rpc_call continue to work because individual test monkeypatches override this fixture.
    """
    from app.services.blockchain import (
        EXPECTED_CHAIN_ID,
        CONTRACT_ADDRESS,
        CHAIN_EVIDENCE_STORE,
        CHAIN_CUSTODY_LOGS,
        BLOCK_HEIGHT,
        _encode_abi_string
    )

    # First check if live Hardhat node is running and responsive
    def is_live_node_active():
        import urllib.request
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8545",
                data=b'{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}',
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=0.05) as resp:
                return resp.status == 200
        except Exception:
            return False

    if not is_live_node_active():
        def mock_rpc_call(method: str, params: list, timeout: float = 2.0) -> dict:
            if method == "eth_chainId":
                return {"jsonrpc": "2.0", "result": hex(EXPECTED_CHAIN_ID), "id": 1}

            elif method == "eth_blockNumber":
                return {"jsonrpc": "2.0", "result": hex(BLOCK_HEIGHT), "id": 1}

            elif method == "eth_getCode":
                target_addr = params[0] if params else ""
                if target_addr and target_addr.lower() == CONTRACT_ADDRESS.lower():
                    # Return realistic deployed Solidity contract runtime bytecode
                    return {"jsonrpc": "2.0", "result": "0x608060405234801561001057600080fd5b50", "id": 1}
                return {"jsonrpc": "2.0", "result": "0x", "id": 1}

            elif method == "eth_call":
                call_obj = params[0] if params else {}
                data = call_obj.get("data", "")
                if data.startswith("0xb16c6ee7"):  # getEvidence(string)
                    raw = bytes.fromhex(data[2:])
                    try:
                        str_offset = int.from_bytes(raw[4:36], "big")
                        str_len = int.from_bytes(raw[4+str_offset:4+str_offset+32], "big")
                        ev_id = raw[4+str_offset+32:4+str_offset+32+str_len].decode("utf-8")
                    except Exception:
                        ev_id = ""

                    if ev_id in CHAIN_EVIDENCE_STORE:
                        rec = CHAIN_EVIDENCE_STORE[ev_id]
                        enc_ev = _encode_abi_string(rec.get("evidence_id", ev_id))
                        enc_case = _encode_abi_string(rec.get("case_id", "CV-2026-001"))
                        enc_hash = _encode_abi_string(rec.get("file_hash", ""))

                        off_ev = 160
                        off_case = off_ev + len(enc_ev)
                        off_hash = off_case + len(enc_case)

                        head0 = off_ev.to_bytes(32, "big")
                        head1 = off_case.to_bytes(32, "big")
                        head2 = off_hash.to_bytes(32, "big")

                        cust = rec.get("custodian", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
                        if cust.startswith("0x") and len(cust) == 42:
                            c_bytes = bytes.fromhex(cust[2:])
                        else:
                            c_bytes = bytes.fromhex("f39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
                        head3 = c_bytes.rjust(32, b"\x00")

                        reg_at = int(rec.get("registered_at", rec.get("timestamp", 1700000000)))
                        head4 = reg_at.to_bytes(32, "big")

                        out_bytes = head0 + head1 + head2 + head3 + head4 + enc_ev + enc_case + enc_hash
                        return {"jsonrpc": "2.0", "result": "0x" + out_bytes.hex(), "id": 1}
                    else:
                        return {"jsonrpc": "2.0", "error": {"code": -32000, "message": "execution reverted: Evidence does not exist"}, "id": 1}
                elif data.startswith("0xae1adffe"):  # getCustodyAnchor(string,uint256)
                    raw = bytes.fromhex(data[2:])
                    try:
                        str_offset = int.from_bytes(raw[4:36], "big")
                        seq = int.from_bytes(raw[36:68], "big")
                        str_len = int.from_bytes(raw[4+str_offset:4+str_offset+32], "big")
                        ev_id = raw[4+str_offset+32:4+str_offset+32+str_len].decode("utf-8")
                    except Exception:
                        ev_id, seq = "", 0

                    from app.services.blockchain import CHAIN_CUSTODY_ANCHORS
                    if ev_id in CHAIN_CUSTODY_ANCHORS and seq in CHAIN_CUSTODY_ANCHORS[ev_id]:
                        anchor = CHAIN_CUSTODY_ANCHORS[ev_id][seq]
                        enc_hash = _encode_abi_string(anchor.get("event_hash", ""))
                        enc_prev = _encode_abi_string(anchor.get("previous_event_hash", ""))
                        off_hash = 192
                        off_prev = off_hash + len(enc_hash)
                        h0 = off_hash.to_bytes(32, "big")
                        h1 = off_prev.to_bytes(32, "big")
                        h2 = int(anchor.get("schema_version", 1)).to_bytes(32, "big")
                        h3 = int(anchor.get("timestamp", int(time.time()))).to_bytes(32, "big")
                        anc_by = anchor.get("anchored_by", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
                        anc_bytes = bytes.fromhex(anc_by[2:] if anc_by.startswith("0x") else "f39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
                        h4 = anc_bytes.rjust(32, b"\x00")
                        h5 = (1).to_bytes(32, "big")  # exists = true
                        out = h0 + h1 + h2 + h3 + h4 + h5 + enc_hash + enc_prev
                        return {"jsonrpc": "2.0", "result": "0x" + out.hex(), "id": 1}
                    else:
                        h_empty = (0).to_bytes(32, "big") * 6
                        return {"jsonrpc": "2.0", "result": "0x" + h_empty.hex(), "id": 1}

                return {"jsonrpc": "2.0", "result": "0x", "id": 1}

            elif method == "eth_sendTransaction":
                tx_obj = params[0] if params else {}
                data = tx_obj.get("data", "")
                if data.startswith("0xb7fe1264"):  # registerEvidence(string,string,string)
                    raw = bytes.fromhex(data[2:])
                    def read_s(off):
                        l = int.from_bytes(raw[4+off:4+off+32], "big")
                        return raw[4+off+32:4+off+32+l].decode("utf-8")
                    off0 = int.from_bytes(raw[4:36], "big")
                    off1 = int.from_bytes(raw[36:68], "big")
                    off2 = int.from_bytes(raw[68:100], "big")
                    ev_id = read_s(off0)
                    case_id = read_s(off1)
                    file_hash = read_s(off2)

                    if ev_id in CHAIN_EVIDENCE_STORE:
                        existing = CHAIN_EVIDENCE_STORE[ev_id]
                        if existing.get("file_hash", "").lower() != file_hash.lower():
                            return {"jsonrpc": "2.0", "error": {"code": -32000, "message": "execution reverted: Evidence already registered with different hash"}, "id": 1}
                        tx_hash = existing.get("tx_hash") or ("0x" + hashlib.sha256(f"{ev_id}:{file_hash}".encode()).hexdigest())
                        return {"jsonrpc": "2.0", "result": tx_hash, "id": 1}

                    tx_hash = "0x" + hashlib.sha256(f"{ev_id}:{file_hash}:{BLOCK_HEIGHT}".encode()).hexdigest()
                    CHAIN_EVIDENCE_STORE[ev_id] = {
                        "evidence_id": ev_id,
                        "case_id": case_id,
                        "file_hash": file_hash,
                        "custodian": tx_obj.get("from", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"),
                        "contract_address": CONTRACT_ADDRESS,
                        "chain_id": EXPECTED_CHAIN_ID,
                        "tx_hash": tx_hash,
                        "block_number": BLOCK_HEIGHT,
                        "registered_at": int(time.time()),
                        "timestamp": int(time.time()),
                        "status": "confirmed"
                    }
                    return {"jsonrpc": "2.0", "result": tx_hash, "id": 1}

                elif data.startswith("0xefd18692"):  # recordCustodyAnchor(string,uint256,string,string,uint256)
                    raw = bytes.fromhex(data[2:])
                    def read_s(off):
                        l = int.from_bytes(raw[4+off:4+off+32], "big")
                        return raw[4+off+32:4+off+32+l].decode("utf-8")
                    off0 = int.from_bytes(raw[4:36], "big")
                    seq = int.from_bytes(raw[36:68], "big")
                    off2 = int.from_bytes(raw[68:100], "big")
                    off3 = int.from_bytes(raw[100:132], "big")
                    ver = int.from_bytes(raw[132:164], "big")
                    ev_id = read_s(off0)
                    ev_hash = read_s(off2)
                    prev_hash = read_s(off3)

                    from app.services.blockchain import CHAIN_CUSTODY_ANCHORS
                    tx_hash = "0x" + hashlib.sha256(f"ANCHOR:{ev_id}:{seq}:{ev_hash}:{BLOCK_HEIGHT}".encode()).hexdigest()
                    if ev_id not in CHAIN_CUSTODY_ANCHORS:
                        CHAIN_CUSTODY_ANCHORS[ev_id] = {}
                    CHAIN_CUSTODY_ANCHORS[ev_id][seq] = {
                        "evidence_id": ev_id,
                        "sequence_number": seq,
                        "event_hash": ev_hash,
                        "previous_event_hash": prev_hash,
                        "schema_version": ver,
                        "contract_address": CONTRACT_ADDRESS,
                        "chain_id": EXPECTED_CHAIN_ID,
                        "tx_hash": tx_hash,
                        "block_number": BLOCK_HEIGHT,
                        "timestamp": int(time.time()),
                        "anchored_by": tx_obj.get("from", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"),
                        "status": "confirmed",
                        "exists": True
                    }
                    return {"jsonrpc": "2.0", "result": tx_hash, "id": 1}

                elif data.startswith("0x6746d252"):  # transferCustody(string,address,string)
                    raw = bytes.fromhex(data[2:])
                    off0 = int.from_bytes(raw[4:36], "big")
                    addr_bytes = raw[36:68][-20:]
                    new_custodian = "0x" + addr_bytes.hex()
                    off2 = int.from_bytes(raw[68:100], "big")
                    def read_s(off):
                        l = int.from_bytes(raw[4+off:4+off+32], "big")
                        return raw[4+off+32:4+off+32+l].decode("utf-8")
                    ev_id = read_s(off0)
                    reason = read_s(off2)

                    if ev_id in CHAIN_EVIDENCE_STORE:
                        CHAIN_EVIDENCE_STORE[ev_id]["custodian"] = new_custodian

                    tx_hash = "0x" + hashlib.sha256(f"{ev_id}:{new_custodian}:{BLOCK_HEIGHT}".encode()).hexdigest()
                    return {"jsonrpc": "2.0", "result": tx_hash, "id": 1}

                return {"jsonrpc": "2.0", "result": "0x" + "1"*64, "id": 1}

            elif method == "eth_getTransactionReceipt":
                tx_hash = params[0] if params else ""
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "transactionHash": tx_hash,
                        "status": "0x1",
                        "blockNumber": hex(BLOCK_HEIGHT),
                        "contractAddress": None
                    },
                    "id": 1
                }
            return {"jsonrpc": "2.0", "result": None, "id": 1}

        monkeypatch.setattr("app.services.blockchain._rpc_call", mock_rpc_call)
    yield

@pytest.fixture
def isolated_storage_dir(monkeypatch, tmp_path):
    """Provide an isolated temporary directory for synthetic evidence files."""
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("STORAGE_PATH", str(evidence_dir))
    yield evidence_dir

@pytest.fixture
def isolated_reports_dir(monkeypatch, tmp_path):
    """Provide an isolated temporary directory for generated forensic reports."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REPORTS_PATH", str(reports_dir))
    yield reports_dir
