自用，测试中

## Build

```pwsh
docker build -t sillytavern2matrix .
```

## Test

```pwsh
docker run -it -v .:/sillytavern2matrix -p 9945:9945 --rm sillytavern2matrix
```

## Run

```pwsh
docker run -d -v .:/sillytavern2matrix -p 9945:9945 --restart unless-stopped --name sillytavern2matrix sillytavern2matrix
```
