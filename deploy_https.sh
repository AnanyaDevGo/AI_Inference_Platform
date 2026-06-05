#!/bin/bash
set -e

echo "=== Step 1: Build frontend Docker image inside minikube ==="
cd /mnt/c/Users/AnanyaPradeep/AI_Inference_Platform/frontend
eval $(minikube docker-env)
docker build -t infervoyage-frontend:latest .
echo "Build complete."

echo ""
echo "=== Step 2: Apply updated k8s manifests ==="
kubectl apply -f /mnt/c/Users/AnanyaPradeep/AI_Inference_Platform/deploy/kubernetes/frontend/service.yaml
kubectl apply -f /mnt/c/Users/AnanyaPradeep/AI_Inference_Platform/deploy/kubernetes/frontend/deployment.yaml
kubectl apply -f /mnt/c/Users/AnanyaPradeep/AI_Inference_Platform/deploy/kubernetes/ingress/ingress.yaml

echo ""
echo "=== Step 3: Restart frontend pod ==="
kubectl rollout restart deployment/frontend -n infervoyage-dev
kubectl rollout status deployment/frontend -n infervoyage-dev --timeout=120s

echo ""
echo "=== Step 4: Enable ssl-passthrough on ingress-nginx ==="
kubectl patch deployment ingress-nginx-controller -n ingress-nginx \
  --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--enable-ssl-passthrough"}]' 2>/dev/null || true

kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=60s

echo ""
echo "All done!"
