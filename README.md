## Build

```pwsh
docker build -t sillytavern2matrix .
```

## Test

```pwsh
docker run -it -v .:/sillytavern2matrix --rm sillytavern2matrix
```

## Run

```pwsh
docker run -d -p 9978:9978 -v .:/sillytavern2matrix --restart unless-stopped --name sillytavern2matrix sillytavern2matrix
```

删除event同时，删除sf聊天记录
one chat one thread
一次性删除整个thread

del chat
switch chat
switch char
list chars
help