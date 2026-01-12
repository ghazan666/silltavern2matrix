## Build

```pwsh
docker build -t sillytavern2matrix .
```

## Test

```pwsh
docker run -it -p 9945:9945 -v .:/sillytavern2matrix --rm sillytavern2matrix
```

## Run

```pwsh
docker run -d -p 9945:9945 -v .:/sillytavern2matrix --restart unless-stopped --network sillytavern_default --name sillytavern2matrix sillytavern2matrix
```
