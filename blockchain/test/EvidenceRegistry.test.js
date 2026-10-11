import { expect } from "chai";
import hre from "hardhat";

describe("EvidenceRegistry Smart Contract & Blockchain Suite", function () {
  let evidenceRegistry;
  let deployer, officer1, officer2;

  beforeEach(async function () {
    [deployer, officer1, officer2] = await hre.ethers.getSigners();
    const EvidenceRegistry = await hre.ethers.getContractFactory("EvidenceRegistry");
    evidenceRegistry = await EvidenceRegistry.deploy();
    await evidenceRegistry.waitForDeployment();
  });

  it("TC-BC-01: Should deploy successfully and set the deployer as the admin", async function () {
    expect(await evidenceRegistry.admin()).to.equal(deployer.address);
  });

  it("TC-BC-02: Should provide isolated test accounts on the local Hardhat network", async function () {
    expect(deployer.address).to.be.a("string");
    expect(officer1.address).to.be.a("string");
    expect(officer1.address).to.not.equal(deployer.address);
  });

  it("TC-BC-03: Successfully registers evidence on-chain with SHA-256 hash", async function () {
    const evidenceId = "EV-001";
    const caseId = "CV-2026-001";
    const fileHash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

    await expect(evidenceRegistry["registerEvidence(string,string,string)"](evidenceId, caseId, fileHash))
      .to.emit(evidenceRegistry, "EvidenceRegistered")
      .withArgs(evidenceId, fileHash, deployer.address, (await hre.ethers.provider.getBlock("latest")).timestamp + 1);

    expect(await evidenceRegistry.doesEvidenceExist(evidenceId)).to.be.true;

    const record = await evidenceRegistry.getEvidence(evidenceId);
    expect(record[0]).to.equal(evidenceId);
    expect(record[1]).to.equal(caseId);
    expect(record[2]).to.equal(fileHash);
    expect(record[3]).to.equal(deployer.address);
  });

  it("TC-BC-04: Successfully transfers custody and emits CustodyTransferred event", async function () {
    const evidenceId = "EV-002";
    const fileHash = "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e";

    await evidenceRegistry["registerEvidence(string,string)"](evidenceId, fileHash);

    await expect(evidenceRegistry["transferCustody(string,address,string)"](evidenceId, officer1.address, "Transferred to forensics lab"))
      .to.emit(evidenceRegistry, "CustodyTransferred")
      .withArgs(evidenceId, deployer.address, officer1.address, (await hre.ethers.provider.getBlock("latest")).timestamp + 1);

    const record = await evidenceRegistry.getEvidence(evidenceId);
    expect(record[3]).to.equal(officer1.address);
    expect(await evidenceRegistry.getCustodyHistoryCount(evidenceId)).to.equal(1);
  });

  it("TC-BC-05: Accurately performs on-chain verification of evidence hash", async function () {
    const evidenceId = "EV-003";
    const authenticHash = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
    const tamperedHash = "0000000000000000000000000000000000000000000000000000000000000000";

    await evidenceRegistry["registerEvidence(string,string)"](evidenceId, authenticHash);

    const matchAuthentic = await evidenceRegistry.verifyEvidence(evidenceId, authenticHash);
    expect(matchAuthentic).to.be.true;

    const matchTampered = await evidenceRegistry.verifyEvidence(evidenceId, tamperedHash);
    expect(matchTampered).to.be.false;
  });

  it("TC-BC-06: Prevents duplicate registration of the same evidence ID", async function () {
    const evidenceId = "EV-004";
    const fileHash = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef";

    await evidenceRegistry["registerEvidence(string,string)"](evidenceId, fileHash);
    await expect(
      evidenceRegistry["registerEvidence(string,string)"](evidenceId, fileHash)
    ).to.be.revertedWith("Evidence already registered");
  });
});
