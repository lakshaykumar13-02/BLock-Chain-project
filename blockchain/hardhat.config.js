import "@nomicfoundation/hardhat-toolbox";
import fs from "fs";
import path from "path";

// Safely attempt to load .env from root or parent directories without external dependency
const candidateEnvPaths = [
  path.resolve(process.cwd(), ".env"),
  path.resolve(process.cwd(), "..", ".env"),
  path.resolve(process.cwd(), "backend", ".env"),
  path.resolve(process.cwd(), "..", "backend", ".env")
];

for (const envPath of candidateEnvPaths) {
  try {
    if (fs.existsSync(envPath) && process.loadEnvFile) {
      process.loadEnvFile(envPath);
      break;
    }
  } catch (e) {
    // ignore
  }
}

// Resolve Sepolia RPC URL, ensuring local Hardhat RPC (127.0.0.1/localhost) is never used for Sepolia
const resolveSepoliaRpc = () => {
  if (process.env.SEPOLIA_RPC_URL && !process.env.SEPOLIA_RPC_URL.includes("127.0.0.1") && !process.env.SEPOLIA_RPC_URL.includes("localhost")) {
    return process.env.SEPOLIA_RPC_URL;
  }
  if (process.env.BLOCKCHAIN_RPC_URL && !process.env.BLOCKCHAIN_RPC_URL.includes("127.0.0.1") && !process.env.BLOCKCHAIN_RPC_URL.includes("localhost")) {
    return process.env.BLOCKCHAIN_RPC_URL;
  }
  return "https://1rpc.io/sepolia";
};

const SEPOLIA_RPC_URL = resolveSepoliaRpc();
const SEPOLIA_PRIVATE_KEY = process.env.SEPOLIA_PRIVATE_KEY || "";

// Helper to validate and clean private key format (must be 64 hex characters)
const getSepoliaAccounts = () => {
  if (!SEPOLIA_PRIVATE_KEY) return [];
  const raw = SEPOLIA_PRIVATE_KEY.startsWith("0x") ? SEPOLIA_PRIVATE_KEY.slice(2) : SEPOLIA_PRIVATE_KEY;
  if (/^[0-9a-fA-F]{64}$/.test(raw)) {
    return [`0x${raw}`];
  }
  return [];
};

const sepoliaAccounts = getSepoliaAccounts();

const networks = {
  hardhat: {},
  localhost: {
    url: "http://127.0.0.1:8545",
  },
  sepolia: {
    url: SEPOLIA_RPC_URL || "https://rpc.sepolia.org",
    chainId: 11155111,
    ...(sepoliaAccounts.length > 0 ? { accounts: sepoliaAccounts } : {})
  }
};

/** @type import('hardhat/config').HardhatUserConfig */
export default {
  solidity: "0.8.19",
  networks,
};
