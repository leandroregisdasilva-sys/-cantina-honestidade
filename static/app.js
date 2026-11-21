// Cantina da Honestidade: máscaras, validação no navegador e pequenas interações.
// O servidor valida tudo de novo antes de gravar; esta camada só dá retorno imediato.
(function () {
  "use strict";

  var digitos = function (t) { return (t || "").replace(/\D/g, ""); };

  // ---------------------------------------------------------------- máscaras
  var mascaras = {
    cpf: function (v) {
      var d = digitos(v).slice(0, 11);
      return d.replace(/(\d{3})(\d)/, "$1.$2")
              .replace(/(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
              .replace(/(\d{3})\.(\d{3})\.(\d{3})(\d)/, "$1.$2.$3-$4");
    },
    // Dinheiro: digita só números e os centavos entram pela direita (1050 -> R$ 10,50)
    dinheiro: function (v) {
      var d = digitos(v).replace(/^0+/, "").slice(0, 8);
      if (!d) return "";
      while (d.length < 3) d = "0" + d;
      var inteiro = d.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
      return "R$ " + inteiro + "," + d.slice(-2);
    },
    inteiro: function (v) { return digitos(v).replace(/^0+(?=\d)/, ""); },
    matricula: function (v) { return (v || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 20); }
  };

  function aplicarMascara(campo) {
    var tipo = campo.dataset.mascara;
    if (mascaras[tipo]) campo.value = mascaras[tipo](campo.value);
  }

  document.querySelectorAll("[data-mascara]").forEach(function (campo) {
    if (campo.value) aplicarMascara(campo);
    campo.addEventListener("input", function () { aplicarMascara(campo); });
  });

  function lerDinheiro(texto) {
    var d = digitos(texto);
    return d ? parseInt(d, 10) / 100 : NaN;
  }

  function cpfValido(cpf) {
    cpf = digitos(cpf);
    if (cpf.length !== 11 || /^(\d)\1{10}$/.test(cpf)) return false;
    for (var pos = 9; pos <= 10; pos++) {
      var soma = 0;
      for (var i = 0; i < pos; i++) soma += Number(cpf[i]) * (pos + 1 - i);
      if ((soma * 10) % 11 % 10 !== Number(cpf[pos])) return false;
    }
    return true;
  }

  function reais(n) { return "R$ " + n.toFixed(2).replace(".", ","); }

  // ---------------------------------------------------------------- validação
  function validar(campo, form) {
    var v = (campo.value || "").trim();
    var tipo = campo.dataset.mascara;
    var min = campo.dataset.min !== undefined ? Number(campo.dataset.min) : null;
    var max = campo.dataset.max !== undefined ? Number(campo.dataset.max) : null;

    if (campo.type === "file") {
      var arq = campo.files && campo.files[0];
      if (!arq) return "";
      if (!/\.(png|jpe?g|webp)$/i.test(arq.name)) return "Envie uma imagem PNG, JPG ou WEBP.";
      if (arq.size > 2 * 1024 * 1024) return "A imagem pode ter até 2 MB.";
      return "";
    }
    if (campo.required && !v) return campo.tagName === "SELECT" ? "Selecione uma opção." : "Campo obrigatório.";
    if (!v) return "";

    if (campo.name === "nome") {
      if (v.split(/\s+/).length < 2) return "Informe nome e sobrenome.";
      if (!/^[A-Za-zÀ-ÿ'. ]+$/.test(v)) return "O nome deve conter apenas letras.";
    }
    if (campo.type === "email" && !/^[\w.+-]+@[\w-]+(\.[\w-]+)+$/.test(v)) return "Informe um e-mail válido, por exemplo nome@senai.br.";
    if (tipo === "cpf" && !cpfValido(v)) return "CPF inválido. Confira os números digitados.";
    if (tipo === "matricula" && !/^[A-Z0-9]{3,20}$/.test(v)) return "Use de 3 a 20 letras ou números.";
    if (tipo === "dinheiro") {
      var valor = lerDinheiro(v);
      if (isNaN(valor)) return "Informe um valor em reais.";
      if (min !== null && valor < min) return "O valor mínimo é " + reais(min) + ".";
      if (max !== null && valor > max) return "O valor máximo é " + reais(max) + ".";
    }
    if (tipo === "inteiro") {
      if (!/^\d+$/.test(v)) return "Informe um número inteiro.";
      var n = parseInt(v, 10);
      if (min !== null && n < min) return "O mínimo é " + min + ".";
      if (max !== null && n > max) return "O máximo é " + max + ".";
    }
    if (campo.minLength > 0 && v.length < campo.minLength) {
      return campo.type === "password" ? "A senha deve ter pelo menos " + campo.minLength + " caracteres."
                                       : "Use pelo menos " + campo.minLength + " caracteres.";
    }
    if (campo.name === "confirmar_senha" && form.elements.senha && v !== form.elements.senha.value) return "As senhas não conferem.";
    return "";
  }

  document.querySelectorAll("form[data-validar]").forEach(function (form) {
    var campos = form.querySelectorAll("input:not([type=hidden]), select, textarea");
    var ajuda = {};
    campos.forEach(function (c) {
      var msg = document.getElementById(c.id + "-msg");
      if (msg && msg.classList.contains("msg-ajuda")) ajuda[c.id] = msg.textContent.trim();
    });

    function marcar(campo, erro) {
      var caixa = campo.closest(".campo");
      var msg = document.getElementById(campo.id + "-msg");
      if (caixa) caixa.classList.toggle("campo-erro", Boolean(erro));
      campo.setAttribute("aria-invalid", erro ? "true" : "false");
      if (msg) { msg.className = erro ? "msg-erro" : "msg-ajuda"; msg.textContent = erro || ajuda[campo.id] || ""; }
    }

    campos.forEach(function (c) {
      c.addEventListener("blur", function () { marcar(c, validar(c, form)); });
      c.addEventListener("change", function () { if (c.type === "file" || c.tagName === "SELECT") marcar(c, validar(c, form)); });
    });

    form.addEventListener("submit", function (e) {
      var primeiro = null;
      campos.forEach(function (c) {
        var erro = validar(c, form);
        marcar(c, erro);
        if (erro && !primeiro) primeiro = c;
      });
      if (primeiro) { e.preventDefault(); primeiro.focus(); }
    });
  });

  // ---------------------------------------------------------------- confirmação
  var dialogo = document.getElementById("dialogo-confirmar");
  var pendente = null;
  document.querySelectorAll("form[data-confirmar]").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (f.dataset.confirmado || !dialogo || !dialogo.showModal) return;
      e.preventDefault();
      pendente = f;
      document.getElementById("dialogo-texto").textContent = f.dataset.confirmar;
      dialogo.showModal();
    });
  });
  if (dialogo) {
    dialogo.addEventListener("click", function (e) {
      var acao = e.target.dataset.acao;
      if (acao === "cancelar" || e.target === dialogo) dialogo.close();
      if (acao === "confirmar" && pendente) { pendente.dataset.confirmado = "1"; pendente.submit(); }
    });
  }

  // ---------------------------------------------------------------- atalhos
  document.querySelectorAll("[data-preencher]").forEach(function (b) {
    b.addEventListener("click", function () {
      var campo = document.getElementById(b.dataset.preencher);
      campo.value = b.dataset.valor;
      aplicarMascara(campo);
      campo.focus();
    });
  });

  document.querySelectorAll("[data-passo]").forEach(function (b) {
    b.addEventListener("click", function () {
      var campo = b.parentElement.querySelector("input");
      var n = (parseInt(campo.value, 10) || 0) + Number(b.dataset.passo);
      var min = Number(campo.dataset.min || 1), max = Number(campo.dataset.max || 99);
      campo.value = Math.min(max, Math.max(min, n));
    });
  });

  document.querySelectorAll("[data-enviar-ao-mudar]").forEach(function (c) {
    c.addEventListener("change", function () { c.form.submit(); });
  });

  document.querySelectorAll("input[data-previa]").forEach(function (c) {
    c.addEventListener("change", function () {
      var arq = c.files && c.files[0];
      var alvo = document.getElementById(c.dataset.previa);
      if (!arq || !/^image\//.test(arq.type)) return;
      var img = document.createElement("img");
      img.className = "foto-previa";
      img.alt = "Prévia da foto";
      img.src = URL.createObjectURL(arq);
      alvo.innerHTML = "";
      alvo.appendChild(img);
    });
  });

  document.querySelectorAll("[data-imprimir]").forEach(function (b) {
    b.addEventListener("click", function () { window.print(); });
  });
})();
