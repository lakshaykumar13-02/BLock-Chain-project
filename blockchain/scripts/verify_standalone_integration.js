import hre from "hardhat";

async function main() {
  console.log("Starting Standalone Hardhat Integration Verification...");

  const network = hre.network.name;
  console.log(`Connected Network: ${network}`);

  const [deployer, officer1] = await hre.ethers.getSigners();
  console.log(`Signer Address: ${deployer.address}`);

  // Attach to deployed contract
  const contractAddress = "0x5FbDB2315678afecb367f032d93F642f64180aa3";
  const EvidenceRegistry = await hre.ethers.getContractFactory("EvidenceRegistry");
  const contract = EvidenceRegistry.attach(contractAddress);

  console.log(`Attached to contract at: ${contractAddress}`);

  // Test 1: Register evidence
  const evidenceId = `EV-STANDALONE-${Date.now()}`;
  const caseId = "CV-STANDALONE-CASE-101";
  const fileHash = "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff";

  console.log(`\n--- Step 1: Register Evidence (${evidenceId}) ---`);
  const tx1 = await contract["registerEvidence(string,string,string)"](evidenceId, caseId, fileHash);
  const receipt1 = await tx1.wait();
  console.log(`Transaction Confirmed: ${receipt1.hash} (Block: ${receipt1.blockNumber})`);

  const exists = await contract.doesEvidenceExist(evidenceId);
  console.log(`Evidence Exists On-Chain: ${exists}`);
  if (!exists) throw new Error("Evidence registration failed to persist");

  // Test 2: Verify on-chain data
  console.log(`\n--- Step 2: Retrieve Evidence Metadata ---`);
  const evidenceData = await contract.getEvidence(evidenceId);
  console.log(`Retrieved Evidence ID: ${evidenceData[0]}`);
  console.log(`Retrieved Case ID: ${evidenceData[1]}`);
  console.log(`Retrieved Hash: ${evidenceData[2]}`);
  console.log(`Retrieved Custodian: ${evidenceData[3]}`);

  // Test 3: Duplicate rejection
  console.log(`\n--- Step 3: Duplicate Rejection ---`);
  let duplicateRejected = false;
  try {
    await contract["registerEvidence(string,string,string)"](evidenceId, caseId, fileHash);
  } catch (err) {
    duplicateRejected = true;
    console.log(`Duplicate correctly rejected: ${err.message.split("\n")[0]}`);
  }
  if (!duplicateRejected) throw new Error("Duplicate registration was not rejected!");

  // Test 4: Transfer Custody
  console.log(`\n--- Step 4: Transfer Custody to Officer 1 ---`);
  const tx2 = await contract["transferCustody(string,address,string)"](
    evidenceId,
    officer1.address,
    "Transferred to forensic examination"
  );
  const receipt2 = await tx2.wait();
  console.log(`Custody Transfer Confirmed: ${receipt2.hash} (Block: ${receipt2.blockNumber})`);

  const updatedData = await contract.getEvidence(evidenceId);
  console.log(`Updated Custodian: ${updatedData[3]}`);
  if (updatedData[3].toLowerCase() !== officer1.address.toLowerCase()) {
    throw new Error("Custodian was not updated on-chain");
  }

  // Test 5: On-chain Verification
  console.log(`\n--- Step 5: On-Chain Hash Verification ---`);
  const isMatch = await contract.verifyEvidence(evidenceId, fileHash);
  const isMismatch = await contract.verifyEvidence(evidenceId, "0000000000000000000000000000000000000000000000000000000000000000");
  console.log(`Authentic Hash Matches: ${isMatch}`);
  console.log(`Tampered Hash Matches: ${isMismatch}`);

  if (!isMatch || isMismatch) throw new Error("On-chain hash verification failed");

  console.log("\n=========================================================");
  console.log("STANDALONE HARDHAT NODE INTEGRATION: 100% SUCCESSFUL");
  console.log("=========================================================");
}

main().catch((err) => {
  console.error("Integration verification failed:", err);
  process.exit(1);
});
