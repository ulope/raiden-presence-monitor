FROM raidennetwork/raiden:latest

ADD presence-monitor.py /

ENTRYPOINT ["/opt/venv/bin/python3", "/presence-monitor.py"]
