const { execSync } = require('child_process');

const clocOut = execSync('cloc .');
console.log(clocOut.toString());
