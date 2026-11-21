"""Controle de acesso: cada área do sistema só abre para o perfil certo."""
from functools import wraps

from flask import flash, redirect, request, session, url_for


def login_obrigatorio(perfil):
    """Libera a rota só para quem entrou com o perfil indicado ('usuario' ou 'funcionario')."""
    def decorador(funcao):
        @wraps(funcao)
        def interna(*args, **kwargs):
            if session.get("perfil") != perfil:
                flash("Entre com seu login para acessar esta página.", "erro")
                return redirect(url_for("login", perfil=perfil, proximo=request.full_path))
            return funcao(*args, **kwargs)
        return interna
    return decorador
