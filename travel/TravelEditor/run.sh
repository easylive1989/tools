#!/bin/bash
set -e
cd "$(dirname "$0")"
make app
open TravelEditor.app
