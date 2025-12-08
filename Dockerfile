# Usa uma imagem leve do Python
FROM python:3.9-slim

# Define a pasta de trabalho
WORKDIR /app

# Copia os requisitos e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto do código
COPY . .

# Expõe a porta 5000 (padrão do Flask/Gunicorn)
EXPOSE 5000

# Comando para rodar o servidor em produção
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
