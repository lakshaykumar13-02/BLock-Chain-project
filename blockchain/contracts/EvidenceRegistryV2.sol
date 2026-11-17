// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title EvidenceRegistryV2
 * @dev Blockchain-Based Digital Evidence Integrity & Cryptographic Custody Anchor Registry
 * 
 * Extends the Phase 1-5 EvidenceRegistry with independent on-chain cryptographic
 * custody event anchoring, sequence verification, and predecessor hash validation.
 * 
 * MIGRATION & COMPATIBILITY:
 * - 100% backward-compatible with all EvidenceRegistry (V1) functions and events:
 *   registerEvidence(string,string,string), registerEvidence(string,string),
 *   transferCustody(string,address,string), transferCustody(string,address),
 *   getEvidence(string), verifyEvidence(string,string), doesEvidenceExist(string),
 *   getCustodyHistoryCount(string).
 * - Deployed V1 contracts continue operating without interruption.
 * - Upgraded deployment allows direct contract-level queries via getCustodyAnchor(string,uint256)
 *   and on-chain enforcement of monotonic sequence and predecessor hash chaining.
 * 
 * STRICT AUTHORIZATION NOTE:
 * This contract is prepared locally for inspection and testing. It MUST NOT be deployed
 * to any live network or testnet without explicit user authorization.
 */
contract EvidenceRegistryV2 {

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

    struct CustodyAnchor {
        string evidenceId;
        uint256 sequenceNumber;
        string eventHash;
        string previousEventHash;
        uint256 schemaVersion;
        uint256 timestamp;
        address anchoredBy;
        bool exists;
    }

    // Mappings
    mapping(string => EvidenceRecord) private evidenceRecords;
    mapping(string => CustodyLog[]) private custodyHistory;
    mapping(string => mapping(uint256 => CustodyAnchor)) private custodyAnchors;
    mapping(string => uint256) private custodyAnchorCounts;

    // Events
    event EvidenceRegistered(string indexed evidenceId, string fileHash, address indexed custodian, uint256 timestamp);
    event CustodyTransferred(string indexed evidenceId, address indexed previousCustodian, address indexed newCustodian, uint256 timestamp);
    event CustodyAnchorRecorded(
        string indexed evidenceId,
        uint256 indexed sequenceNumber,
        string eventHash,
        string previousEventHash,
        uint256 schemaVersion,
        address indexed anchoredBy,
        uint256 timestamp
    );

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

    // =========================================================================
    // V1 BACKWARD-COMPATIBLE REGISTRATION FUNCTIONS
    // =========================================================================

    /**
     * @dev Register forensic evidence hash on-chain with case ID (V1 compatible)
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
     * @dev Overloaded registerEvidence with 2 parameters for convenience (V1 compatible)
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

    // =========================================================================
    // V2 CUSTODY ANCHORING FUNCTIONS (EXACT CANONICAL HASH ANCHORING)
    // =========================================================================

    /**
     * @dev Anchor an exact canonical custody event hash on-chain.
     * Enforces monotonic sequence continuity and cryptographic predecessor link on-chain.
     * 
     * @param evidenceId The unique evidence identifier
     * @param sequenceNumber Strictly monotonic sequence (1, 2, 3...)
     * @param eventHash The 64-character SHA-256 canonical hash of the custody event
     * @param previousEventHash Preceding event hash ('GENESIS' for sequence 1)
     * @param schemaVersion Event schema version (e.g. 1)
     */
    function recordCustodyAnchor(
        string memory evidenceId,
        uint256 sequenceNumber,
        string memory eventHash,
        string memory previousEventHash,
        uint256 schemaVersion
    ) external evidenceExists(evidenceId) {
        require(bytes(evidenceId).length > 0, "Evidence ID cannot be empty");
        EvidenceRecord storage record = evidenceRecords[evidenceId];
        require(msg.sender == record.custodian || msg.sender == admin, "Unauthorized to anchor custody event");
        require(sequenceNumber > 0, "Sequence number must be positive");
        require(bytes(eventHash).length == 64, "Event hash must be 64-character SHA-256 hex");
        require(bytes(previousEventHash).length > 0, "Previous event hash cannot be empty");
        require(!custodyAnchors[evidenceId][sequenceNumber].exists, "Anchor already recorded for this sequence");

        // Sequence continuity & predecessor link validation
        if (sequenceNumber > 1) {
            require(custodyAnchors[evidenceId][sequenceNumber - 1].exists, "Preceding sequence anchor does not exist");
            require(
                keccak256(bytes(custodyAnchors[evidenceId][sequenceNumber - 1].eventHash)) == keccak256(bytes(previousEventHash)),
                "Previous event hash does not match prior on-chain anchor"
            );
        } else {
            require(
                keccak256(bytes(previousEventHash)) == keccak256(bytes("GENESIS")),
                "Genesis anchor must have previousEventHash 'GENESIS'"
            );
        }

        custodyAnchors[evidenceId][sequenceNumber] = CustodyAnchor({
            evidenceId: evidenceId,
            sequenceNumber: sequenceNumber,
            eventHash: eventHash,
            previousEventHash: previousEventHash,
            schemaVersion: schemaVersion,
            timestamp: block.timestamp,
            anchoredBy: msg.sender,
            exists: true
        });

        if (sequenceNumber > custodyAnchorCounts[evidenceId]) {
            custodyAnchorCounts[evidenceId] = sequenceNumber;
        }

        emit CustodyAnchorRecorded(
            evidenceId,
            sequenceNumber,
            eventHash,
            previousEventHash,
            schemaVersion,
            msg.sender,
            block.timestamp
        );
    }

    /**
     * @dev Retrieve on-chain custody anchor for independent verification.
     */
    function getCustodyAnchor(
        string memory evidenceId,
        uint256 sequenceNumber
    ) external view evidenceExists(evidenceId) returns (
        string memory eventHash,
        string memory previousEventHash,
        uint256 schemaVersion,
        uint256 timestamp,
        address anchoredBy,
        bool exists
    ) {
        CustodyAnchor memory anchor = custodyAnchors[evidenceId][sequenceNumber];
        return (
            anchor.eventHash,
            anchor.previousEventHash,
            anchor.schemaVersion,
            anchor.timestamp,
            anchor.anchoredBy,
            anchor.exists
        );
    }

    /**
     * @dev Retrieve total number of anchored custody events for an evidence record.
     */
    function getCustodyAnchorCount(
        string memory evidenceId
    ) external view evidenceExists(evidenceId) returns (uint256) {
        return custodyAnchorCounts[evidenceId];
    }

    // =========================================================================
    // V1 BACKWARD-COMPATIBLE CUSTODY TRANSFER & QUERY FUNCTIONS
    // =========================================================================

    /**
     * @dev Transfer custody of evidence to a new address with reason (V1 compatible)
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
     * @dev Overloaded transferCustody without reason string (V1 compatible)
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
     * @dev Verify if a given file hash matches the on-chain recorded hash (V1 compatible)
     */
    function verifyEvidence(
        string memory evidenceId,
        string memory checkHash
    ) external view evidenceExists(evidenceId) returns (bool) {
        return keccak256(bytes(evidenceRecords[evidenceId].fileHash)) == keccak256(bytes(checkHash));
    }

    /**
     * @dev Get evidence record details (V1 compatible)
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
     * @dev Check if evidence exists (V1 compatible)
     */
    function doesEvidenceExist(string memory evidenceId) external view returns (bool) {
        return evidenceRecords[evidenceId].exists;
    }

    /**
     * @dev Get custody transfer logs count (V1 compatible)
     */
    function getCustodyHistoryCount(string memory evidenceId) external view evidenceExists(evidenceId) returns (uint256) {
        return custodyHistory[evidenceId].length;
    }
}
