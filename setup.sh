#!/bin/bash
set +e  # don't stop on errors
wget https://www.sqlite.org/2025/sqlite-tools-linux-x64-3490100.zip
unzip sqlite-tools-linux-x64-3490100.zip sqlite3
sudo mv sqlite3 /usr/local/bin/sqlite3
sudo chmod +x /usr/local/bin/sqlite3

/usr/local/bin/sqlite3 data/meridant.db < seed.sql
/usr/local/bin/sqlite3 data/meridant_frameworks.db < seed_frameworks.sql
chmod +x start.sh