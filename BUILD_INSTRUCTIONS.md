# Guia de Compilação do APK (Android)

Este documento descreve o processo para gerar o arquivo `.apk` de instalação do NotifyInvest manualmente, usando o ambiente local que já está configurado.

## 📋 Pré-requisitos

Certifique-se de que o ambiente de desenvolvimento Android (Java/JDK, Android SDK) está configurado no computador (o que já deve estar, pois já compilamos antes).

## 🚀 Passo a Passo

### 1. Abrir o Terminal

Abra o terminal na pasta raiz do projeto (`notifyinvest`).

### 2. (Opcional) Sincronizar Configurações

Se você alterou ícones, nomes ou configurações no `app.json`, rode este comando na pasta `mobile` para garantir que o projeto nativo Android seja atualizado:

```powershell
cd mobile
npx expo prebuild
```

### 3. Compilar o APK

Navegue até a pasta android e execute o `gradlew`.

```powershell
# Se estiver na raiz do projeto:
cd mobile\android

# Comando de Build (Release)
.\gradlew assembleRelease
```

> **Nota:** Esse processo pode levar alguns minutos (download de dependências, compilação do código nativo, etc).

### 4. Localizar o Arquivo Gerado

Ao finalizar (aparecerá `BUILD SUCCESSFUL`), o arquivo `.apk` estará disponível no seguinte caminho:

📂 **Caminho:** `notifyinvest\mobile\android\app\build\outputs\apk\release`
📄 **Arquivo:** `app-release.apk`

---

## 📲 Instalação

1. Copie o arquivo `app-release.apk` para o seu celular (via USB, Google Drive, WhatsApp, etc).
2. No celular, clique no arquivo para instalar.
   - Pode ser necessário permitir "Instalar de fontes desconhecidas" ou ignorar o aviso do Play Protect (pois estamos usando uma chave de assinatura de debug/desenvolvimento).

## 🛠 Solução de Problemas Comuns

- **Erro de Permissão:** Se o comando `.\gradlew` for negado, tente rodar o terminal como Administrador.
- **Erro de Memória:** Se o build falhar com erro de Java Heap Space, feche outros programas pesados (VS Code, Chrome) e tente novamente.
- **Limpeza:** Se o build falhar estranhamente, rode `.\gradlew clean` antes de tentar o `assembleRelease` novamente.
