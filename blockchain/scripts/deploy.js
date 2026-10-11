import hre from "hardhat";
import fs from "fs";
import path from "path";

async function main() {
  console.log("Starting deployment...");

  const network = hre.network.name;
  console.log(`Deploying to network: ${network}`);

  const [deployer] = await hre.ethers.getSigners();
  console.log(`Deployer Address: ${deployer.address}`);

  const EvidenceRegistry = await hre.ethers.getContractFactory("EvidenceRegistry");
  const evidenceRegistry = await EvidenceRegistry.deploy();

  await evidenceRegistry.waitForDeployment();

  const contractAddress = await evidenceRegistry.getAddress();
  const txHash = evidenceRegistry.deploymentTransaction().hash;

  console.log("=====================================");
  console.log("Contract Name: EvidenceRegistry");
  console.log(`Contract Address: ${contractAddress}`);
  console.log(`Network: ${network}`);
  console.log(`Deployment Transaction Hash: ${txHash}`);
  console.log(`Deployer Address: ${deployer.address}`);
  console.log("=====================================");

  const artifactsDir = path.join(process.cwd(), "deployments");
  if (!fs.existsSync(artifactsDir)) {
    fs.mkdirSync(artifactsDir, { recursive: true });
  }

  const artifact = await hre.artifacts.readArtifact("EvidenceRegistry");

  const deploymentInfo = {
    contractName: "EvidenceRegistry",
    address: contractAddress,
    network: network,
    deployer: deployer.address,
    transactionHash: txHash,
    abi: artifact.abi,
    timestamp: new Date().toISOString()
  };

  fs.writeFileSync(
    path.join(artifactsDir, `${network}_EvidenceRegistry.json`),
    JSON.stringify(deploymentInfo, null, 2)
  );

  console.log(`Deployment artifact saved to deployments/${network}_EvidenceRegistry.json`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
