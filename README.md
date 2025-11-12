# Benchmark-of-Typescript-Projects

# Run Script getRepo
1. setup .env with a github token
2. setup python
3. install packages "pip install requests GitPython python-dotenv"
4. python scripts/getRepo.py


# Get Docker Image Running
1. open -a "Docker" 

2. docker build -t tsbench:dev .

3. docker run --rm -it -v "$PWD":/work -e GITHUB_TOKEN tsbench:dev \
  python3 scripts/freeze_corpus.py

4. docker run --rm -it -v "$PWD":/work tsbench:dev \
  python3 scripts/getRepo.py

5. docker run --rm -it -v "$PWD":/work tsbench:dev \
  node scripts/bench.js
