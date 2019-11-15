#!/bin/sh

docker build build -f build/$1.Dockerfile -t iomirea/run-lang-$1
docker push iomirea/run-lang-$1
