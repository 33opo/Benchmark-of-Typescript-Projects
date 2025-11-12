FROM node:20-bullseye-slim

# run the OS tools we need
RUN apt-get update && apt-get install -y --no-install-recommends \
    git time python3 python3-pip ca-certificates openssh-client \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g pnpm@10.18.3
# optional noise reducers:
RUN npm config set fund false && npm config set audit false

# install python dependencies
RUN python3 -m pip install --no-cache-dir requests

# set the TypeScript version used by bench scripts
ENV TS_VERSION=5.6.3
ENV NODE_OPTIONS=--max-old-space-size=8192

# mount the repo
WORKDIR /work
CMD ["bash"]