#!/usr/bin/env python3
"""Mede imagens lado a lado e emite a tabela do estudo de caso em Markdown.

Chamado pelo workflow comparacao.yml, mas roda igual na máquina local:

    python3 .github/scripts/comparar.py \\
        --imagem "2018 publicada:cirolini/flask-uwsgi:latest" \\
        --imagem "2026:comp:2026"

Duas contagens de CVE são reportadas de propósito. A bruta é a que aparece em
slide de fornecedor; a de corrigíveis é a que alguém consegue agir. Elas
divergem MUITO entre distribuições: o Debian rastreia e publica CVEs menores
que decide não corrigir, e o banco do Alpine lista sobretudo o que já foi
corrigido. Comparar contagem bruta entre distros mede política de rastreamento,
não risco.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter

NAO_CONSTROI = "NAO_CONSTROI"


def sh(*args: str) -> str:
    """Roda um comando e devolve stdout, ou string vazia se falhar."""
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=900, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as erro:
        print(f"aviso: {' '.join(args)} falhou: {erro}", file=sys.stderr)
        return ""


def cves(imagem: str, so_corrigiveis: bool) -> Counter[str] | None:
    """Conta CVEs por severidade. None se o scan não rodou."""
    cmd = ["trivy", "image", "--quiet", "--scanners", "vuln", "--format", "json"]
    if so_corrigiveis:
        cmd.append("--ignore-unfixed")
    cmd.append(imagem)

    bruto = sh(*cmd)
    if not bruto:
        return None

    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        return None

    return Counter(
        v["Severity"]
        for r in dados.get("Results") or []
        for v in r.get("Vulnerabilities") or []
    )


def medir(rotulo: str, imagem: str) -> dict[str, object]:
    if imagem == NAO_CONSTROI:
        return {"rotulo": rotulo, "constroi": False}

    inspect = sh(
        "docker", "image", "inspect", imagem,
        "--format", "{{.Size}}|{{.Architecture}}|{{len .RootFS.Layers}}|{{.Config.User}}",
    )
    tamanho, arch, camadas, usuario = (inspect.split("|") + ["", "", "", ""])[:4]

    # `docker images` mostra o tamanho descompactado em disco; o .Size do
    # inspect, com o image store do containerd, é a soma dos blobs comprimidos
    # — que é o que se baixa da rede. Os dois interessam, por motivos
    # diferentes, e confundi-los faz a comparação mentir.
    disco = sh("docker", "images", "--format", "{{.Size}}", imagem).splitlines()

    todos = cves(imagem, so_corrigiveis=False)
    corrigiveis = cves(imagem, so_corrigiveis=True)

    python_v = sh("docker", "run", "--rm", "--entrypoint", "python", imagem, "-V")
    uid = sh("docker", "run", "--rm", "--entrypoint", "id", imagem, "-u")

    return {
        "rotulo": rotulo,
        "constroi": True,
        "comprimido": int(tamanho) if tamanho.isdigit() else 0,
        "disco": disco[0] if disco else "?",
        "arch": arch,
        "camadas": camadas,
        "usuario": usuario or f"uid {uid}" if uid else usuario,
        "python": python_v.replace("Python ", "") or "?",
        "todos": todos,
        "corrigiveis": corrigiveis,
    }


def mib(n: int) -> str:
    return f"{n / 1048576:.1f} MiB" if n else "?"


def linha_cve(c: Counter[str] | None) -> str:
    if c is None:
        return "scan falhou"
    total = sum(c.values())
    if not total:
        return "**0**"
    partes = [f"{c[s]}{s[0]}" for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW") if c[s]]
    return f"**{total}** ({' / '.join(partes)})"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--imagem", action="append", default=[], metavar="ROTULO:IMAGEM")
    p.add_argument("--build-2019", default="?")
    p.add_argument("--build-2026", default="?")
    args = p.parse_args()

    medidas = []
    for spec in args.imagem:
        rotulo, _, imagem = spec.partition(":")
        medidas.append(medir(rotulo, imagem))

    saida: list[str] = ["## Comparação 2019 vs 2026", ""]

    quebrada = [m for m in medidas if not m["constroi"]]
    if quebrada:
        saida += [
            "> O Dockerfile de 2019 **não constrói mais** em amd64. Isso não foi",
            "> alterado por ninguém: o `FROM python:3-alpine` e o `Flask` sem versão",
            "> fixada apontam hoje para software que não existia quando o arquivo",
            "> foi escrito.",
            "",
        ]

    ok = [m for m in medidas if m["constroi"]]
    if not ok:
        print("\n".join(saida))
        return 0

    cab = "| | " + " | ".join(str(m["rotulo"]) for m in ok) + " |"
    sep = "|---|" + "---|" * len(ok)

    def linha(titulo: str, chave) -> str:
        return f"| {titulo} | " + " | ".join(str(chave(m)) for m in ok) + " |"

    saida += [
        cab,
        sep,
        linha("Python", lambda m: m["python"]),
        linha("Arquitetura", lambda m: m["arch"]),
        linha("Pull (comprimido)", lambda m: mib(m["comprimido"])),
        linha("Disco", lambda m: m["disco"]),
        linha("Camadas", lambda m: m["camadas"]),
        linha("Usuário", lambda m: m["usuario"] or "root"),
        linha("CVEs corrigíveis", lambda m: linha_cve(m["corrigiveis"])),
        linha("CVEs totais", lambda m: linha_cve(m["todos"])),
        "",
        f"Build: 2019 em {args.build_2019}s, 2026 em {args.build_2026}s "
        "(runner amd64 nativo, sem cache).",
        "",
        "**CVEs totais incluem o que não tem correção disponível.** Debian e",
        "Alpine rastreiam vulnerabilidade com políticas diferentes, então a",
        "contagem bruta entre distros compara política, não risco. A linha que",
        "importa para decidir alguma coisa é a de corrigíveis.",
    ]

    print("\n".join(saida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
