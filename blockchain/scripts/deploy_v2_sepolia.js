import hre from "hardhat";
import fs from "fs";
import path from "path";

import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Safely attempt to load root or parent .env files without external dependencies
function loadEnvIfPresent() {
  const candidateEnvPaths = [
    path.resolve(process.cwd(), ".env"),
    path.resolve(process.cwd(), "..", ".env"),
    path.resolve(__dirname, "..", "..", ".env"),
    path.resolve(__dirname, "..", "..", "backend", ".env")
  ];
  for (const envPath of candidateEnvPaths) {
    try {
      if (fs.existsSync(envPath) && process.loadEnvFile) {
        process.loadEnvFile(envPath);
        break;
      }
    } catch (e) {
      // Ignore if not readable
    }
  }
}

async function main() {
  loadEnvIfPresent();

  const network = hre.network.name;
  console.log(`===============================================`);
  console.log(`ChainVault V2 Deployment Script (Dry-Run Guarded)`);
  console.log(`Target Network: ${network}`);
  console.log(`===============================================`);

  const rpcUrl = process.env.SEPOLIA_RPC_URL || (process.env.BLOCKCHAIN_RPC_URL && !process.env.BLOCKCHAIN_RPC_URL.includes("127.0.0.1") && !process.env.BLOCKCHAIN_RPC_URL.includes("localhost") ? process.env.BLOCKCHAIN_RPC_URL : "");
  const privateKey = process.env.SEPOLIA_PRIVATE_KEY;
  const deployBroadcast = process.env.DEPLOY_BROADCAST === "true";

  // Pre-flight validation for Sepolia
  if (network === "sepolia") {
    const hasValidRpc = rpcUrl && !rpcUrl.includes("YOUR_INFURA") && !rpcUrl.includes("PROJECT_ID");
    const cleanKey = privateKey ? (privateKey.startsWith("0x") ? privateKey.slice(2) : privateKey) : "";
    const hasValidKey = cleanKey.length === 64 && /^[0-9a-fA-F]{64}$/.test(cleanKey);

    if (deployBroadcast) {
      if (!hasValidRpc) {
        console.error("FATAL: SEPOLIA_RPC_URL environment variable is missing, invalid, or contains placeholder values.");
        console.error("Expected format: https://eth-sepolia.g.alchemy.com/v2/<API_KEY> or https://sepolia.infura.io/v3/<PROJECT_ID>");
        process.exit(1);
      }
      if (!hasValidKey) {
        console.error("FATAL: SEPOLIA_PRIVATE_KEY is missing or invalid.");
        console.error("Requirements: A 64-character hexadecimal Ethereum private key (with or without '0x' prefix).");
        console.error("Note: Do NOT use an Etherscan or Alchemy API key (e.g. 32-34 character strings). A private key must be exported from your wallet (MetaMask / cast / Hardhat account).");
        process.exit(1);
      }
    } else {
      if (!hasValidRpc) {
        console.log("Notice: SEPOLIA_RPC_URL is not configured yet (not required for dry-run).");
      }
      if (!hasValidKey) {
        console.log("Notice: SEPOLIA_PRIVATE_KEY is not configured yet (not required for dry-run).");
      }
    }
  }

  // Verify contract artifact can be loaded
  console.log("Loading contract artifact for EvidenceRegistryV2...");
  const EvidenceRegistryV2 = await hre.ethers.getContractFactory("EvidenceRegistryV2");
  console.log("EvidenceRegistryV2 factory compiled and loaded successfully.");

  // SAFETY GUARD: Refuse to broadcast unless explicitly commanded
  if (!deployBroadcast) {
    console.log("-----------------------------------------------");
    console.log("SAFETY GUARD ACTIVE: DEPLOY_BROADCAST is not set to 'true'.");
    console.log("Dry-run validation successful. No transactions were broadcast.");
    console.log("To broadcast to a network, set DEPLOY_BROADCAST=true and provide necessary credentials.");
    console.log("-----------------------------------------------");
    return;
  }

  // Live deployment path (only reachable if DEPLOY_BROADCAST=true)
  const [deployer] = await hre.ethers.getSigners();
  const netInfo = await hre.ethers.provider.getNetwork();
  const chainId = Number(netInfo.chainId);

  console.log(`Deployer address: ${deployer.address}`);
  console.log(`Target Chain ID: ${chainId}`);

  const evidenceRegistryV2 = await EvidenceRegistryV2.deploy();
  await evidenceRegistryV2.waitForDeployment();

  const contractAddress = await evidenceRegistryV2.getAddress();
  const txHash = evidenceRegistryV2.deploymentTransaction()?.hash || "unknown";

  console.log("=====================================");
  console.log("Contract Name: EvidenceRegistryV2");
  console.log(`Contract Address: ${contractAddress}`);
  console.log(`Network: ${network}`);
  console.log(`Chain ID: ${chainId}`);
  console.log(`Transaction Hash: ${txHash}`);
  console.log(`Deployer Address: ${deployer.address}`);
  console.log("=====================================");

  // Explicitly anchor to blockchain/deployments directory so artifacts are never misplaced or overwritten
  const artifactsDir = path.resolve(__dirname, "..", "deployments");
  if (!fs.existsSync(artifactsDir)) {
    fs.mkdirSync(artifactsDir, { recursive: true });
  }

  const artifact = await hre.artifacts.readArtifact("EvidenceRegistryV2");
  // Security guarantee: Only public on-chain identifiers are saved. Never store private keys or RPC credentials.
  const deploymentInfo = {
    contractName: "EvidenceRegistryV2",
    address: contractAddress,
    network: network,
    chainId: chainId,
    deployer: deployer.address,
    transactionHash: txHash,
    abi: artifact.abi,
    timestamp: new Date().toISOString()
  };

  const artifactPath = path.join(artifactsDir, `${network}_EvidenceRegistryV2.json`);
  fs.writeFileSync(artifactPath, JSON.stringify(deploymentInfo, null, 2));
  console.log(`Deployment artifact saved to ${artifactPath}`);
}

main().catch((error) => {
  console.error("Deployment script failed:", error.message || error);
  process.exitCode = 1;
});
