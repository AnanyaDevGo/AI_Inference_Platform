#!/bin/bash
set -e

echo "=== Enabling SSL passthrough on ingress-nginx ==="
kubectl patch deployment ingress-nginx-controller -n ingress-nginx \
  --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--enable-ssl-passthrough"}]'

echo "Waiting for ingress-nginx to roll out..."
kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=90s

echo ""
echo "=== Waiting for frontend (new TLS pod) to be ready ==="
kubectl rollout status deployment/frontend -n infervoyage-dev --timeout=90s

echo ""
echo "=== All pods status ==="
kubectl get pods -n infervoyage-dev
kubectl get pods -n monitoring | grep grafana
kubectl get pods -n infervoyage-dev | grep locust

echo ""
echo "=== Ingress status ==="
kubectl get ingress -n infervoyage-dev

echo "Done!"
