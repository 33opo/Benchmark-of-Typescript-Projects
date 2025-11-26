# Benchmark-of-Typescript-Projects

# Run Script getRepo
1. setup .env with a github token
2. setup python
3. install packages "pip install requests GitPython python-dotenv"
4. python scripts/getRepo.py

# SCRIPTS
1. freeze_corpus.py: Freeze the benchmark corpus to concrete Git commit SHAs.
- Finds the latest commit on the default branch.
- Writes two log files under logs/:
* corpus.jsonl — json lock file
* CORPUS.md — human-readable table

2. getRepo.py: Take a frozen corpus from corpus.jsonl
- Clone/checkout each repository at its locked commit_sha into projects/
- Get basic code size metadata per repo

3. bench.js: logs TypeScript compiler output
- scan projects folder
- install dependencies for each project
- searches for tsconfig.json file (tsconfig tells the TypeScript compiler what to compile and how to compile it)
- returns different metadata such as 
* Files, Lines, Memory used, Total time
* Exit code (success/failure)
* Wall time (measured around the tsc call)
- outputs the logs and the overall summary in /logs

# Get Docker Image Running
1. open -a "Docker" or just open docker manually

2. docker build -t tsbench:dev .

3. docker run --rm -it -v "$PWD":/work -e GITHUB_TOKEN tsbench:dev \
  python3 scripts/freeze_corpus.py

4. docker run --rm -it -v "$PWD":/work tsbench:dev \
  python3 scripts/getRepo.py

5. docker run --rm -it -v "$PWD":/work tsbench:dev \
  node scripts/bench.js
