FROM node:16.16.0-alpine as build

COPY . /frontend
WORKDIR /frontend

RUN npm ci
RUN npm run build
