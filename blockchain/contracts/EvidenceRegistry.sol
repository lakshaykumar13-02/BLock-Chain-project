// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title EvidenceRegistry
 * @dev Blockchain-Based Digital Evidence Integrity & Chain-of-Custody Registry
 */
contract EvidenceRegistry {

    address public admin;

    struct EvidenceRecord {
        string evidenceId;
        string caseId;
        string fileHash;
        address custodian;
        uint256 registeredAt;
        bool exists;
    }

    struct CustodyLog {
        address previousCustodian;
        address newCustodian;
        uint256 timestamp;
        string reason;
    }

    // Mappings
    mapping(string => EvidenceRecord) private evidenceRecords;
    mapping(string => CustodyLog[]) private custodyHistory;

    // Events
    event EvidenceRegistered(string indexed evidenceId, string fileHash, address indexed custodian, uint256 timestamp);
    event CustodyTransferred(string indexed evidenceId, address indexed previousCustodian, address indexed newCustodian, uint256 timestamp);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin can perform this operation");
        _;
    }

    modifier evidenceExists(string memory evidenceId) {
        require(evidenceRecords[evidenceId].exists, "Evidence does not exist");
        _;
    }

    constructor() {
        admin = msg.sender;
    }

    /**
     * @dev Register forensic evidence hash on-chain with case ID
     */
    function registerEvidence(
        string memory evidenceId,
        string memory caseId,
        string memory fileHash
    ) external {
        require(bytes(evidenceId).length > 0, "Evidence ID cannot be empty");
        require(bytes(fileHash).length > 0, "File hash cannot be empty");
        require(!evidenceRecords[evidenceId].exists, "Evidence already registered");

        evidenceRecords[evidenceId] = EvidenceRecord({
            evidenceId: evidenceId,
            caseId: caseId,
            fileHash: fileHash,
            custodian: msg.sender,
            registeredAt: block.timestamp,
            exists: true
        });

        emit EvidenceRegistered(evidenceId, fileHash, msg.sender, block.timestamp);
    }

    /**
     * @dev Overloaded registerEvidence with 2 parameters for convenience
     */
    function registerEvidence(
        string memory evidenceId,
        string memory fileHash
    ) external {
        require(bytes(evidenceId).length > 0, "Evidence ID cannot be empty");
        require(bytes(fileHash).length > 0, "File hash cannot be empty");
        require(!evidenceRecords[evidenceId].exists, "Evidence already registered");

        evidenceRecords[evidenceId] = EvidenceRecord({
            evidenceId: evidenceId,
            caseId: "GENERAL",
            fileHash: fileHash,
            custodian: msg.sender,
            registeredAt: block.timestamp,
            exists: true
        });

        emit EvidenceRegistered(evidenceId, fileHash, msg.sender, block.timestamp);
    }

    /**
     * @dev Transfer custody of evidence to a new address with reason
     */
    function transferCustody(
        string memory evidenceId,
        address newCustodian,
        string memory reason
    ) external evidenceExists(evidenceId) {
        require(newCustodian != address(0), "Invalid custodian address");
        EvidenceRecord storage record = evidenceRecords[evidenceId];
        require(msg.sender == record.custodian || msg.sender == admin, "Unauthorized to transfer custody");

        address prev = record.custodian;
        record.custodian = newCustodian;

        custodyHistory[evidenceId].push(CustodyLog({
            previousCustodian: prev,
            newCustodian: newCustodian,
            timestamp: block.timestamp,
            reason: reason
        }));

        emit CustodyTransferred(evidenceId, prev, newCustodian, block.timestamp);
    }

    /**
     * @dev Overloaded transferCustody without reason string
     */
    function transferCustody(
        string memory evidenceId,
        address newCustodian
    ) external evidenceExists(evidenceId) {
        require(newCustodian != address(0), "Invalid custodian address");
        EvidenceRecord storage record = evidenceRecords[evidenceId];
        require(msg.sender == record.custodian || msg.sender == admin, "Unauthorized to transfer custody");

        address prev = record.custodian;
        record.custodian = newCustodian;

        custodyHistory[evidenceId].push(CustodyLog({
            previousCustodian: prev,
            newCustodian: newCustodian,
            timestamp: block.timestamp,
            reason: "Standard transfer"
        }));

        emit CustodyTransferred(evidenceId, prev, newCustodian, block.timestamp);
    }

    /**
     * @dev Verify if a given file hash matches the on-chain recorded hash
     */
    function verifyEvidence(
        string memory evidenceId,
        string memory checkHash
    ) external view evidenceExists(evidenceId) returns (bool) {
        return keccak256(bytes(evidenceRecords[evidenceId].fileHash)) == keccak256(bytes(checkHash));
    }

    /**
     * @dev Get evidence record details
     */
    function getEvidence(
        string memory evidenceId
    ) external view evidenceExists(evidenceId) returns (
        string memory,
        string memory,
        string memory,
        address,
        uint256
    ) {
        EvidenceRecord memory record = evidenceRecords[evidenceId];
        return (
            record.evidenceId,
            record.caseId,
            record.fileHash,
            record.custodian,
            record.registeredAt
        );
    }

    /**
     * @dev Check if evidence exists
     */
    function doesEvidenceExist(string memory evidenceId) external view returns (bool) {
        return evidenceRecords[evidenceId].exists;
    }

    /**
     * @dev Get custody transfer logs count
     */
    function getCustodyHistoryCount(string memory evidenceId) external view evidenceExists(evidenceId) returns (uint256) {
        return custodyHistory[evidenceId].length;
    }
}
