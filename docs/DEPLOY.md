# IntelliCodeX Server Deployment Guide (Phase 1)

This guide walks you through deploying the IntelliCodeX backend on a rented Cloud GPU (e.g., RunPod, Lambda Labs, AWS, or Paperspace).

## 1. Provision a Cloud GPU
Rent a Linux machine (Ubuntu 22.04 recommended) with at least:
- **GPU**: RTX 3090 / 4090 or A4000 / A5000 (16-24 GB VRAM)
- **Disk**: 50 GB+ persistent storage
- Ensure ports `80` and `443` are open in the provider's firewall if you are accessing it publicly.

## 2. Install Ollama and Pull Models
SSH into your cloud machine and install Ollama:
```bash
curl -fsSL https://ollama.com/install.sh | sh
```
Pull the required AI models:
```bash
ollama run qwen2.5-coder:14b
ollama pull nomic-embed-text
```

## 3. Clone and Start the Server
Clone your IntelliCodeX repository onto the cloud machine.

Navigate to the `deploy` directory:
```bash
cd IntelliCodeX/deploy
```

Set a secure JWT secret and start the Docker cluster:
```bash
export JWT_SECRET="your_super_secret_random_string"
docker-compose -f docker-compose.prod.yml up -d
```

## 4. Test the Connection
From your *local laptop*, run this `curl` command replacing `YOUR_SERVER_IP` with the cloud instance's IP address:
```bash
curl http://YOUR_SERVER_IP/api/health
```
If it returns a healthy status, your server is officially deployed and ready for Phase 2!
