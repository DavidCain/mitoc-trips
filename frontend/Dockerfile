FROM node:12.22.3-alpine as build

COPY . /frontend
WORKDIR /frontend

RUN npm ci
RUN npm run build
