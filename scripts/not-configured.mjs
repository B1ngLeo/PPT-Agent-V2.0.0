const [scope = "unknown", ownerGoal = "unspecified"] = process.argv.slice(2);

console.log(`${scope}: not-configured (owned by ${ownerGoal})`);
