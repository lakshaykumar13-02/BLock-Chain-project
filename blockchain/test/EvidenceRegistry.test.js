import { expect } from "chai";
import hre from "hardhat";

describe("EvidenceRegistry Skeleton Contract (Phase 1 Baseline)", function () {
  it("Should set the deployer as the admin", async function () {
    const [deployer] = await hre.ethers.getSigners();
    const EvidenceRegistry = await hre.ethers.getContractFactory("EvidenceRegistry");
    const evidenceRegistry = await EvidenceRegistry.deploy();
    await evidenceRegistry.waitForDeployment();

    expect(await evidenceRegistry.admin()).to.equal(deployer.address);
  });
});
