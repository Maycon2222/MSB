# Automacoes MSB

Aplicacao desktop em Python para tratar XMLs de NF-e, planilhas Excel/CSV e relatorios auxiliares usados nas rotinas da MSB.

## Funcionalidades

- Conversao de XML de NF-e para planilha Excel, com uma linha por item da nota.
- Geracao de referencias antigas com limite configuravel em meses.
- Busca de texto no campo de observacao da NF-e.
- Tratamento de planilhas por filtros e comparacao entre arquivos.
- Conversao de CSV para XLSX.
- Rotinas auxiliares para relatorios SIEG, BM010/DataSul e geracao de DANFE em PDF.
- Interface grafica com abas para XML NF-e, analise XML e SIEG.

## Requisitos

- Python 3.11 ou superior.
- Windows para uso completo da interface e automacoes com tela.

## Instalacao

```bash
pip install -r requirements.txt
```

## Como executar

Interface grafica:

```bash
python -m automacao_correcao.gui
```

Menu pelo terminal:

```bash
python -m automacao_correcao
```

No Windows, tambem e possivel abrir pelos arquivos:

- `executar_interface.bat`
- `abrir_interface.vbs`

## Instalacao em outro computador

Execute:

```bat
instalar.bat
```

O instalador instala as dependencias, copia o app para a pasta local do usuario e cria o atalho `Automacoes MSB` na area de trabalho.

## Observacoes sobre dados

Arquivos reais de XML, Excel, CSV, PDF, logs, backups e saidas geradas ficam fora do Git por padrao. Use o repositorio apenas para o codigo-fonte, assets e testes.
