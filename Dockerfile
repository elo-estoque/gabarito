# Usa uma imagem leve do Python
FROM python:3.9-slim

# Instala dependências do sistema necessárias para manipular imagens (Pillow)
RUN apt-get update && apt-get install -y \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Define a pasta de trabalho
WORKDIR /app

# Copia os requisitos e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto do código
COPY . .

# Expõe a porta 5000
EXPOSE 5000

# Comando para rodar o servidor
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
