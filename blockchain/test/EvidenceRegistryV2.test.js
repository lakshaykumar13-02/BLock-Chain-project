import { expect } from "chai";
import hre from "hardhat";

describe("EvidenceRegistryV2 Smart Contract — Local EVM Suite", function () {
  let evidenceRegistryV2;
  let deployer, custodianOfficer, unauthorizedOfficer;

  const validEvidenceId = "EV-EVM-001";
  const validCaseId = "CV-EVM-2026-001";
  const validFileHash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

  // Deterministic 64-character SHA-256 hex strings
  const genesisEventHash = "1111111111111111111111111111111111111111111111111111111111111111";
  const sequence2EventHash = "2222222222222222222222222222222222222222222222222222222222222222";
  const sequence3EventHash = "3333333333333333333333333333333333333333333333333333333333333333";

  beforeEach(async function () {
    [deployer, custodianOfficer, unauthorizedOfficer] = await hre.ethers.getSigners();
    const EvidenceRegistryV2 = await hre.ethers.getContractFactory("EvidenceRegistryV2");
    evidenceRegistryV2 = await EvidenceRegistryV2.deploy();
    await evidenceRegistryV2.waitForDeployment();

    // Register test evidence under custodianOfficer
    await evidenceRegistryV2.connect(custodianOfficer)["registerEvidence(string,string,string)"](
      validEvidenceId,
      validCaseId,
      validFileHash
    );
  });

  it("TC-EVM-01: Successfully deploys EvidenceRegistryV2 and verifies admin", async function () {
    expect(await evidenceRegistryV2.admin()).to.equal(deployer.address);
    expect(await evidenceRegistryV2.doesEvidenceExist(validEvidenceId)).to.be.true;
  });

  it("TC-EVM-02: Successfully anchors Genesis custody event and retrieves record independently", async function () {
    const tx = await evidenceRegistryV2.connect(custodianOfficer).recordCustodyAnchor(
      validEvidenceId,
      1,
      genesisEventHash,
      "GENESIS",
      1
    );
    const receipt = await tx.wait();

    // Check event emission
    await expect(tx)
      .to.emit(evidenceRegistryV2, "CustodyAnchorRecorded")
      .withArgs(
        validEvidenceId,
        1,
        genesisEventHash,
        "GENESIS",
        1,
        custodianOfficer.address,
        (await hre.ethers.provider.getBlock("latest")).timestamp
      );

    // Retrieve via independent getter
    const anchor = await evidenceRegistryV2.getCustodyAnchor(validEvidenceId, 1);
    expect(anchor.eventHash).to.equal(genesisEventHash);
    expect(anchor.previousEventHash).to.equal("GENESIS");
    expect(anchor.schemaVersion).to.equal(1n);
    expect(anchor.anchoredBy).to.equal(custodianOfficer.address);
    expect(anchor.exists).to.be.true;
    expect(await evidenceRegistryV2.getCustodyAnchorCount(validEvidenceId)).to.equal(1n);
  });

  it("TC-EVM-03: Successfully anchors consecutive sequence 2 and verifies cryptographic link continuity", async function () {
    // Anchor sequence 1 (Genesis)
    await evidenceRegistryV2.connect(custodianOfficer).recordCustodyAnchor(
      validEvidenceId,
      1,
      genesisEventHash,
      "GENESIS",
      1
    );

    // Anchor sequence 2 linking to genesisEventHash
    await evidenceRegistryV2.connect(custodianOfficer).recordCustodyAnchor(
      validEvidenceId,
      2,
      sequence2EventHash,
      genesisEventHash,
      1
    );

    const anchor2 = await evidenceRegistryV2.getCustodyAnchor(validEvidenceId, 2);
    expect(anchor2.eventHash).to.equal(sequence2EventHash);
    expect(anchor2.previousEventHash).to.equal(genesisEventHash);
    expect(anchor2.exists).to.be.true;
    expect(await evidenceRegistryV2.getCustodyAnchorCount(validEvidenceId)).to.equal(2n);
  });

  it("TC-EVM-04: Rejects out-of-order sequence (gap/missing predecessor anchor)", async function () {
    // Attempt sequence 2 before sequence 1 exists
    await expect(
      evidenceRegistryV2.connect(custodianOfficer).recordCustodyAnchor(
        validEvidenceId,
        2,
        sequence2EventHash,
        genesisEventHash,
        1
      )
    ).to.be.revertedWith("Preceding sequence anchor does not exist");
  });

  it("TC-EVM-05: Rejects broken predecessor hash link in consecutive sequence", async function () {
    // Anchor sequence 1
    await evidenceRegistryV2.connect(custodianOfficer).recordCustodyAnchor(
      validEvidenceId,
      1,
      genesisEventHash,
      "GENESIS",
      1
    );

    // Sequence 2 with fraudulent previousEventHash
    const tamperedPrevHash = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff";
    await expect(
      evidenceRegistryV2.connect(custodianOfficer).recordCustodyAnchor(
        validEvidenceId,
        2,
        sequence2EventHash,
        tamperedPrevHash,
        1
      )
    ).to.be.revertedWith("Previous event hash does not match prior on-chain anchor");
  });

  it("TC-EVM-06: Rejects sequence 1 if previousEventHash is not 'GENESIS'", async function () {
    await expect(
      evidenceRegistryV2.connect(custodianOfficer).recordCustodyAnchor(
        validEvidenceId,
        1,
        genesisEventHash,
        "NOT_GENESIS",
        1
      )
    ).to.be.revertedWith("Genesis anchor must have previousEventHash 'GENESIS'");
  });

  it("TC-EVM-07: Rejects duplicate anchoring for the same sequence number", async function () {
    await evidenceRegistryV2.connect(custodianOfficer).recordCustodyAnchor(
      validEvidenceId,
      1,
      genesisEventHash,
      "GENESIS",
      1
    );

    await expect(
      evidenceRegistryV2.connect(custodianOfficer).recordCustodyAnchor(
        validEvidenceId,
        1,
        genesisEventHash,
        "GENESIS",
        1
      )
    ).to.be.revertedWith("Anchor already recorded for this sequence");
  });

  it("TC-EVM-08: Validates hash formatting (rejects non-64-char hex strings)", async function () {
    // Too short (32 chars)
    await expect(
      evidenceRegistryV2.connect(custodianOfficer).recordCustodyAnchor(
        validEvidenceId,
        1,
        "short_hash_123456789012345678901",
        "GENESIS",
        1
      )
    ).to.be.revertedWith("Event hash must be 64-character SHA-256 hex");

    // Too long (65 chars)
    await expect(
      evidenceRegistryV2.connect(custodianOfficer).recordCustodyAnchor(
        validEvidenceId,
        1,
        genesisEventHash + "a",
        "GENESIS",
        1
      )
    ).to.be.revertedWith("Event hash must be 64-character SHA-256 hex");
  });

  it("TC-EVM-09: Rejects unauthorized caller (not active custodian and not admin)", async function () {
    await expect(
      evidenceRegistryV2.connect(unauthorizedOfficer).recordCustodyAnchor(
        validEvidenceId,
        1,
        genesisEventHash,
        "GENESIS",
        1
      )
    ).to.be.revertedWith("Unauthorized to anchor custody event");
  });

  it("TC-EVM-10: Allows contract admin to anchor records even if not current custodian", async function () {
    await expect(
      evidenceRegistryV2.connect(deployer).recordCustodyAnchor(
        validEvidenceId,
        1,
        genesisEventHash,
        "GENESIS",
        1
      )
    ).to.emit(evidenceRegistryV2, "CustodyAnchorRecorded");
  });

  it("TC-EVM-11: Rejects anchor operations for non-existent evidence IDs", async function () {
    await expect(
      evidenceRegistryV2.connect(deployer).recordCustodyAnchor(
        "EV-NONEXISTENT",
        1,
        genesisEventHash,
        "GENESIS",
        1
      )
    ).to.be.revertedWith("Evidence does not exist");
  });
});
