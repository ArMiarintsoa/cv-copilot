# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Empêcher Python de générer des fichiers .pyc et forcer l'affichage immédiat des logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Dépendances système :
# - curl : pour les healthchecks
# - dépendances graphiques & polices pour WeasyPrint (libpango, cairo, gdk-pixbuf, libffi, fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copie du code source du projet
COPY . .

# Création du dossier de stockage des sessions
RUN mkdir -p /app/data/sessions

EXPOSE 8000 8501
