# FROM python:3.14.2
# WORKDIR /code

# # Prevent Python from writing pyc files & enable unbuffered logs
# ENV PYTHONDONTWRITEBYTECODE=1
# ENV PYTHONUNBUFFERED=1

# # Install the application dependencies
# COPY ./requirements.txt /code/requirements.txt
# RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# # Copy in the source code
# COPY ./app /code/app
# EXPOSE 8000

# CMD ["fastapi", "run", "app/main.py", "--port", "8000"]


# ----------------- Stage 1: Builder -----------------
FROM python:3.12.10-slim as builder

ENV PYTHONUNBUFFERED=1

# Create working directory
WORKDIR /code

# Install system build dependencies and add GDAL PPA
RUN apt-get update && \
	apt-get install -y --no-install-recommends \
	curl \
	libpangocairo-1.0-0 \
	libpq-dev \
	python-dev-is-python3 \
	libproj-dev \
	libc-dev \
	binutils \
	gettext \
	make \
	cmake \
	gcc \
	g++ \
	gdal-bin \
	libgdal-dev && \
	rm -rf /var/lib/apt/lists/* && \
	apt-get autoremove -y && \
	apt-get clean

# GDAL include paths
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Install Python dependencies with uv
COPY requirements.txt ./
RUN uv pip install -r requirements.txt --system --no-cache && \
	rm requirements.txt
