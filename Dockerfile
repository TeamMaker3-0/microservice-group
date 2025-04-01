# group-microservice/Dockerfile

# Utiliza una imagen base de Python (ajusta la versión si es necesario)
FROM python:3.9-slim

# Define el directorio de trabajo dentro del contenedor
WORKDIR /group-microservice

# Copia el archivo de requerimientos e instala las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de la aplicación
COPY . .

# Expone el puerto en el que FastAPI escuchará (en este ejemplo, 3003)
EXPOSE 3003

# Comando para arrancar la aplicación con uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3003", "--reload"]
