# PControl

Controle o PC pelo celular: ver a tela ao vivo, usar como touchpad e teclado, abrir apps e jogos da Steam, tocar vídeos do YouTube, volume e mídia, desligar/reiniciar, arquivos e processos.

Funciona **no Wi-Fi de casa** e **de qualquer lugar** (pelo Tailscale, uma rede privada gratuita entre o seu celular e o seu PC).

**Precisa de:** Windows 10 ou 11, [Python 3.11 ou mais novo](https://www.python.org/downloads/) (marque *"Add python.exe to PATH"* ao instalar) e um celular Android.

---

## Instalar (uma vez só)

### 1. No PC

Baixe o projeto: botão verde **Code → Download ZIP** aqui no GitHub (depois extraia), ou:

```
git clone https://github.com/USUARIO/PControl.git
```

Na pasta do projeto, dê dois cliques em **`configurar.bat`**. Ele:

1. instala o que precisa;
2. pede a **senha** que o celular vai usar para entrar (você escolhe);
3. coloca o PControl para **abrir sozinho junto com o Windows**;
4. libera o PControl no Firewall (o Windows vai pedir permissão de administrador);
5. abre uma página com **QR codes** para o celular.

### 2. No celular (Android)

1. Escaneie o QR code **"Baixe o app"** e instale o `PControl.apk` (ou baixe direto da página de [Releases](https://github.com/USUARIO/PControl/releases/latest)). O Android vai pedir para permitir "instalar apps desconhecidos": permita para o navegador. Como o APK não vem da Play Store, o Play Protect pode avisar que o app é desconhecido: toque em *Instalar mesmo assim*.
2. Abra o PControl. No Wi-Fi de casa ele **acha o PC sozinho**. Toque no PC e entre com a senha.

> **iPhone:** não existe APK. Abra o endereço do QR code "Wi-Fi de casa" no Safari e use *Compartilhar → Adicionar à Tela de Início*.

### 3. Para usar fora de casa

1. Instale o **Tailscale** (https://tailscale.com/download) **no PC e no celular** e entre com a **mesma conta** nos dois.
2. No PC, no ícone do Tailscale perto do relógio, ative **"Run unattended"** (assim ele conecta mesmo antes de você entrar no Windows).
3. Em casa, abra o PControl uma vez: ele aprende o endereço do Tailscale sozinho.

Pronto: fora de casa, deixe o app do Tailscale ligado no celular e abra o PControl. Ele tenta o Wi-Fi primeiro e, se não achar, vai pelo Tailscale, sem você precisar fazer nada.

---

## Ligar o PC e já usar

- O PControl abre sozinho **quando você entra na sua conta do Windows**.
- Se o seu Windows pede senha ou PIN ao ligar, o PControl só começa depois que alguém entrar. Para não precisar disso, dá para ativar o **login automático** do Windows (pelo `netplwiz` ou pelo programa *Autologon* da Microsoft). Atenção: com isso, qualquer pessoa que ligar o PC entra direto na sua conta.
- A opção **"Manter o PC acordado"** (aba Controles) vem ligada para o PC não suspender sozinho e sumir do alcance.
- Ligar um PC **desligado** pelo celular não é possível por aqui.

---

## Como usar

### Tela
- **Touchpad:** arraste 1 dedo para mover o mouse, toque para clicar, toque duas vezes para clique duplo, toque e logo em seguida arraste para segurar e arrastar. **2 dedos** rolam a página; toque com 2 dedos = clique direito.
- **Toque direto:** toque exatamente onde quer clicar. Segure para clique direito.
- **Lupa (+/−):** zoom; a imagem acompanha o mouse.
- **⚙ (barras):** qualidade da imagem, quadros por segundo e velocidade do touchpad. Fora de casa ou no 4G, use **Econômica**.
- **⌨ Teclado:** toque no campo e digite: o texto vai direto para o PC, com acento e tudo. Tem Ctrl, Alt, Shift, Win, setas e atalhos (copiar, colar, Alt+Tab, Alt+F4…).
- **Tela cheia:** botão no canto. Deite o celular para ter a tela do PC maior.

### Apps
- **Abertos agora:** toque para mostrar, minimizar ou fechar.
- **Jogos da Steam** com capa, e **todos os apps** do menu Iniciar. Toque e ele abre no PC.
- **Favoritos:** qualquer arquivo (um `.exe` de jogo, por exemplo) vira favorito pela aba Arquivos → *Fixar em Apps*. Ele abre **na pasta onde está**, como se você tivesse clicado duas vezes nele.

### YouTube
- Pesquise ou cole um link e toque no vídeo: ele toca no navegador do PC.
- Embaixo fica o controle: anterior, −10 s, play/pausa, +10 s, próximo, mudo e tela cheia.
- No app do YouTube do celular: **Compartilhar → PControl** toca o vídeo direto no PC.

### Controles
Volume, play/pausa, **digitar ou colar texto** no PC, pegar o que está copiado no PC, abrir um link, **bloquear / desligar tela / suspender / reiniciar / desligar** (dá para agendar e cancelar), desempenho e gerenciador de tarefas.

### Arquivos
Navegue pelas pastas, **envie** arquivos do celular para o PC, **baixe** do PC, veja fotos, vídeos e textos, abra no PC, renomeie ou mande para a Lixeira.

---

## O que não dá para fazer (limites do Windows)

- **Tela de bloqueio e avisos do administrador (UAC):** o Windows não deixa nenhum programa comum ver ou clicar neles. Se bloquear o PC estando longe, só desbloqueia quem estiver na frente dele.
- **Janelas abertas como administrador** não recebem cliques do PControl.
- Alguns **jogos em tela cheia exclusiva** aparecem pretos na transmissão. Use o modo *janela sem borda* do jogo.
- Os botões do controle do YouTube vão para a janela que está na frente no PC (normalmente o navegador que abriu o vídeo).

---

## Segurança

- Só entra quem tem a senha. Cada aparelho fica logado por até 90 dias (*Controles → Sair deste aparelho*).
- O PControl só aceita conexões da **rede local** e do **Tailscale**. Nada fica aberto na internet.
- **Trocar a senha** (desconecta todos os aparelhos):
  ```
  .venv\Scripts\python.exe server.py --senha
  ```
- Para aceitar **só pelo Tailscale** (nunca pelo Wi-Fi), mude `"allow_lan": true` para `false` no `config.json` e reinicie o PControl.

---

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `configurar.bat` | Instala, define a senha, coloca para abrir com o Windows e libera no firewall |
| `iniciar.bat` | Roda com uma janela aberta (bom para ver erros) |
| `parar.bat` | Para o PControl que está rodando escondido |
| `pcontrol.log` | Registro de quando ele roda escondido |
| `config.json` | Configurações (porta, Wi-Fi permitido, favoritos) |
| `android\build.bat` | Recompila o APK (precisa do Android Studio) |
| `tools\startup.ps1 -Remove` | Tira o PControl da inicialização do Windows |

## Problemas comuns

- **O app não acha o PC:** o PC está ligado e com alguém logado? O celular está no mesmo Wi-Fi? No PC, abra `http://localhost:8765/conectar`, veja o endereço e digite ele no app (⚙ → *Conectar*).
- **Fora de casa não conecta:** o Tailscale está ligado no celular e no PC, com a mesma conta? Abriu o PControl em casa pelo menos uma vez depois de instalar o Tailscale?
- **Imagem lenta:** ⚙ → qualidade *Econômica* e 10 quadros por segundo.
