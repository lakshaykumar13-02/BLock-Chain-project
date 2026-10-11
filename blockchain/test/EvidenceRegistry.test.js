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

  it("TC-BC-03 (Gap Audit): Identifies missing registerEvidence function on skeleton contract", async function () {
    // Audit check: Verify whether Phase 5 on-chain registration function is present
    const hasRegisterFunction = typeof evidenceRegistry.registerEvidence === "function";
    // In Phase 1 skeleton, this is expected to be false (documented gap)
    expect(hasRegisterFunction).to.be.false;
  });

  it("TC-BC-04 (Gap Audit): Identifies missing transferCustody function on skeleton contract", async function () {
    const hasTransferFunction = typeof evidenceRegistry.transferCustody === "function";
    expect(hasTransferFunction).to.be.false;
  });

  it("TC-BC-05 (Gap Audit): Identifies missing verifyEvidence function on skeleton contract", async function () {
    const hasVerifyFunction = typeof evidenceRegistry.verifyEvidence === "function";
    expect(hasVerifyFunction).to.be.false;
  });
});
