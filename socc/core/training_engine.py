"""
training_engine.py
Motor de Machine Learning do SOCC baseado nos arquivos Pensamento_Ofensa_*.md.

Fluxo:
  1. PensamentoParser  →  lê os arquivos .md e extrai registros estruturados
  2. TrainingEngine    →  vetoriza (TF-IDF), treina classificador e salva o modelo
  3. TrainingEngine    →  infere classificação e casos similares para novos payloads

O modelo treina automaticamente quando novos arquivos de Pensamento são detectados.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import warnings
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
MODEL_VERSION = "training-v1"
MODEL_FILENAME = "model.joblib"
VECTORIZER_FILENAME = "vectorizer.joblib"
MANIFEST_FILENAME = "training_manifest.json"

# Mapa de rótulos curtos → rótulos canônicos
_LABEL_MAP: dict[str, str] = {
    "btp": "Benign True Positive",
    "benign true positive": "Benign True Positive",
    "tp": "True Positive",
    "true positive": "True Positive",
    "fp": "False Positive",
    "false positive": "False Positive",
    "tn": "True Negative",
    "true negative": "True Negative",
    "log transmission failure": "Log Transmission Failure",
    "ltf": "Log Transmission Failure",
}

# Seções que carregam o conteúdo analítico para vetorização
_ANALYSIS_SECTIONS = {
    "2. análise",
    "3. investigação",
    "4. detalhamento",
}


# ---------------------------------------------------------------------------
# Estrutura de um caso de treinamento
# ---------------------------------------------------------------------------
@dataclass
class TrainingRecord:
    ofensa_id: str
    cliente: str
    tipo_alerta: str
    classificacao: str           # rótulo canônico
    texto_evidencia: str         # seções 2 + 3
    texto_raciocinio: str        # seção 4
    texto_completo: str          # tudo junto (usado para vetorização)
    arquivo: str
    fingerprint: str             # sha256 do conteúdo do arquivo

    def label(self) -> str:
        return self.classificacao

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Parser de arquivos Pensamento_Ofensa_*.md
# ---------------------------------------------------------------------------
class PensamentoParser:
    """Extrai registros estruturados de arquivos Pensamento_Ofensa_*.md."""

    # Regex para capturar o ID da ofensa e o cliente a partir do título
    _TITLE_RE = re.compile(
        r"^#\s+Fluxo\s+de\s+Pensamento.*?Ofensa\s+(\d+)\s*\(([^)]+)\)",
        re.IGNORECASE | re.MULTILINE,
    )

    # Regex para capturar o tipo de alerta ("O quê:" na seção 1)
    _ALERT_TYPE_RE = re.compile(
        r"[-*]\s+\*{0,2}O\s+qu[êe]\s*:\*{0,2}\s+(.+)",
        re.IGNORECASE,
    )

    # Detecta rótulos de classificação no texto
    _CLASSIFICATION_RE = re.compile(
        r"\b(Benign\s+True\s+Positive|True\s+Positive|False\s+Positive|"
        r"True\s+Negative|Log\s+Transmission\s+Failure|BTP|TP|FP|TN|LTF)\b",
        re.IGNORECASE,
    )

    def parse_file(self, path: Path) -> TrainingRecord | None:
        """Lê um arquivo .md e retorna um TrainingRecord ou None se inválido."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        fingerprint = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

        # --- ID e cliente ---
        title_match = self._TITLE_RE.search(text)
        ofensa_id = title_match.group(1) if title_match else path.stem
        cliente = title_match.group(2).strip() if title_match else "Desconhecido"

        # --- Tipo de alerta ---
        alert_match = self._ALERT_TYPE_RE.search(text)
        tipo_alerta = alert_match.group(1).strip() if alert_match else ""

        # --- Fatiar seções ---
        secoes = self._split_sections(text)
        texto_evidencia = "\n".join(
            content
            for heading, content in secoes.items()
            if any(s in heading.lower() for s in ("2.", "3."))
        )
        texto_raciocinio = "\n".join(
            content
            for heading, content in secoes.items()
            if "4." in heading
        )

        # --- Classificação ---
        classificacao = self._extract_classification(text)
        if not classificacao:
            return None  # arquivo sem classificação identificável

        texto_completo = text.strip()

        return TrainingRecord(
            ofensa_id=ofensa_id,
            cliente=cliente,
            tipo_alerta=tipo_alerta,
            classificacao=classificacao,
            texto_evidencia=texto_evidencia,
            texto_raciocinio=texto_raciocinio,
            texto_completo=texto_completo,
            arquivo=str(path),
            fingerprint=fingerprint,
        )

    def parse_directory(self, directory: Path) -> list[TrainingRecord]:
        """Lê todos os Pensamento_Ofensa_*.md de um diretório."""
        records: list[TrainingRecord] = []
        for path in sorted(directory.glob("Pensamento_Ofensa_*.md")):
            record = self.parse_file(path)
            if record:
                records.append(record)
        return records

    # --- helpers internos ---

    def _split_sections(self, text: str) -> dict[str, str]:
        """Divide o markdown em {heading: conteúdo}."""
        sections: dict[str, str] = {}
        current_heading = "__preamble__"
        current_lines: list[str] = []
        for line in text.splitlines():
            if re.match(r"^##\s+", line):
                sections[current_heading] = "\n".join(current_lines).strip()
                current_heading = line.lstrip("# ").strip()
                current_lines = []
            else:
                current_lines.append(line)
        sections[current_heading] = "\n".join(current_lines).strip()
        return sections

    def _extract_classification(self, text: str) -> str:
        """Extrai a classificação final do texto; prioriza padrões próximos de palavras-chave."""
        # Prioridade: "Classificação Final:", "classifico como", "Classificação:"
        priority_patterns = [
            r"(?:Classifica[çc][aã]o\s+Final|classifico\s+como)[:\s]+\**([^.\n*]+)",
            r"\*\*Classificação:\*\*\s*([^\n]+)",
            r"Classificação:\s+([^\n]+)",
        ]
        for pattern in priority_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                label = self._normalize_label(m.group(1).strip())
                if label:
                    return label

        # Fallback: encontra todos e pega o mais frequente
        found = self._CLASSIFICATION_RE.findall(text)
        if not found:
            return ""
        counts: dict[str, int] = {}
        for raw in found:
            label = self._normalize_label(raw)
            if label:
                counts[label] = counts.get(label, 0) + 1
        return max(counts, key=lambda k: counts[k]) if counts else ""

    def _normalize_label(self, raw: str) -> str:
        key = raw.strip().lower()
        return _LABEL_MAP.get(key, "")


# ---------------------------------------------------------------------------
# Motor de treinamento e inferência
# ---------------------------------------------------------------------------
class TrainingEngine:
    """
    Treina um classificador scikit-learn sobre os arquivos Pensamento_Ofensa_*.md
    e expõe métodos de inferência para novos payloads/eventos.
    """

    def __init__(self, training_dir: str | Path, model_dir: str | Path | None = None):
        self.training_dir = Path(training_dir).expanduser().resolve()
        if model_dir is None:
            self.model_dir = self.training_dir.parent / "training_model"
        else:
            self.model_dir = Path(model_dir).expanduser().resolve()
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._vectorizer = None
        self._records: list[TrainingRecord] = []
        self._parser = PensamentoParser()

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def _manifest_path(self) -> Path:
        return self.model_dir / MANIFEST_FILENAME

    def _model_path(self) -> Path:
        return self.model_dir / MODEL_FILENAME

    def _vectorizer_path(self) -> Path:
        return self.model_dir / VECTORIZER_FILENAME

    def _load_manifest(self) -> dict[str, Any]:
        p = self._manifest_path()
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_manifest(self, records: list[TrainingRecord]) -> None:
        manifest = {
            "version": MODEL_VERSION,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "n_samples": len(records),
            "training_dir": str(self.training_dir),
            "files": {
                rec.arquivo: rec.fingerprint for rec in records
            },
            "label_distribution": self._label_distribution(records),
        }
        self._manifest_path().write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _label_distribution(self, records: list[TrainingRecord]) -> dict[str, int]:
        dist: dict[str, int] = {}
        for rec in records:
            dist[rec.classificacao] = dist.get(rec.classificacao, 0) + 1
        return dist

    # ------------------------------------------------------------------
    # Controle de estado
    # ------------------------------------------------------------------

    def is_trained(self) -> bool:
        return self._model_path().exists() and self._vectorizer_path().exists()

    def is_stale(self) -> bool:
        """Retorna True se novos arquivos foram adicionados desde o último treino."""
        if not self.is_trained():
            return True
        manifest = self._load_manifest()
        saved_files: dict[str, str] = manifest.get("files", {})
        current_files = {
            str(p): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in sorted(self.training_dir.glob("Pensamento_Ofensa_*.md"))
        }
        return current_files != saved_files

    # ------------------------------------------------------------------
    # Treinamento
    # ------------------------------------------------------------------

    def train(self, *, force: bool = False) -> dict[str, Any]:
        """
        Treina o modelo com todos os arquivos Pensamento_Ofensa_*.md.
        Retorna um resumo com métricas básicas.
        """
        import joblib
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.neighbors import KNeighborsClassifier
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import LabelEncoder

        if not force and not self.is_stale():
            return {"status": "skipped", "reason": "Modelo já atualizado."}

        records = self._parser.parse_directory(self.training_dir)
        if len(records) < 2:
            return {
                "status": "error",
                "reason": f"Amostras insuficientes: {len(records)} (mínimo: 2).",
            }

        # Corpus: vetorizar texto completo de cada caso
        corpus = [rec.texto_completo for rec in records]
        labels = [rec.classificacao for rec in records]

        # Número de vizinhos: no máximo 5, no mínimo 1 e menor que n_amostras
        k = min(5, max(1, len(records) - 1))

        vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            max_features=5000,
            sublinear_tf=True,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            X = vectorizer.fit_transform(corpus)

        clf = KNeighborsClassifier(
            n_neighbors=k,
            metric="cosine",
            algorithm="brute",
        )
        clf.fit(X, labels)

        joblib.dump(clf, self._model_path())
        joblib.dump(vectorizer, self._vectorizer_path())
        self._save_manifest(records)

        # Guarda em memória para inferência imediata
        self._model = clf
        self._vectorizer = vectorizer
        self._records = records

        return {
            "status": "ok",
            "n_samples": len(records),
            "k_neighbors": k,
            "label_distribution": self._label_distribution(records),
            "model_path": str(self._model_path()),
        }

    # ------------------------------------------------------------------
    # Carregamento do modelo
    # ------------------------------------------------------------------

    def load(self) -> bool:
        """Carrega o modelo salvo em disco. Retorna True se bem-sucedido."""
        if not self.is_trained():
            return False
        try:
            import joblib
            self._model = joblib.load(self._model_path())
            self._vectorizer = joblib.load(self._vectorizer_path())
            self._records = self._parser.parse_directory(self.training_dir)
            return True
        except Exception:
            return False

    def _ensure_loaded(self) -> bool:
        if self._model is not None and self._vectorizer is not None:
            return True
        return self.load()

    # ------------------------------------------------------------------
    # Inferência
    # ------------------------------------------------------------------

    def predict(self, text: str) -> dict[str, Any]:
        """
        Infere classificação para um novo payload/texto de evento.

        Retorna:
          predicted_classification  – rótulo previsto
          confidence                – proporção de vizinhos com o rótulo previsto (0–1)
          similar_cases             – lista de casos similares com scores
          reasoning_hints           – fragmentos de raciocínio dos casos mais próximos
          model_available           – False se o modelo não estiver treinado
        """
        if not self._ensure_loaded():
            return {
                "model_available": False,
                "predicted_classification": None,
                "confidence": 0.0,
                "similar_cases": [],
                "reasoning_hints": [],
                "message": "Modelo não treinado. Execute: socc train",
            }

        X_query = self._vectorizer.transform([text])

        # Previsão com probabilidade de votos dos vizinhos
        predicted = self._model.predict(X_query)[0]
        distances, indices = self._model.kneighbors(X_query)

        neighbor_labels = [self._records[i].classificacao for i in indices[0]]
        confidence = neighbor_labels.count(predicted) / len(neighbor_labels)

        # Casos similares (distância coseno → similaridade)
        similar_cases: list[dict[str, Any]] = []
        for dist, idx in zip(distances[0], indices[0]):
            rec = self._records[idx]
            similarity = round(float(1.0 - dist), 4)
            similar_cases.append({
                "ofensa_id": rec.ofensa_id,
                "cliente": rec.cliente,
                "tipo_alerta": rec.tipo_alerta,
                "classificacao": rec.classificacao,
                "similaridade": similarity,
                "arquivo": rec.arquivo,
            })

        # Dicas de raciocínio: fragmentos das seções de evidência dos casos mais próximos
        reasoning_hints = self._extract_reasoning_hints(indices[0])

        return {
            "model_available": True,
            "predicted_classification": predicted,
            "confidence": round(confidence, 4),
            "similar_cases": similar_cases,
            "reasoning_hints": reasoning_hints,
        }

    def format_context(self, prediction: dict[str, Any], *, max_chars: int = 1200) -> str:
        """
        Formata o resultado da inferência ML como bloco de texto para injetar
        no knowledge_context do pipeline de análise.
        """
        if not prediction.get("model_available"):
            return ""

        label = prediction.get("predicted_classification", "N/A")
        conf = prediction.get("confidence", 0.0)
        conf_pct = f"{conf * 100:.0f}%"

        lines: list[str] = [
            "=== Contexto de Aprendizado (ML Training Engine) ===",
            f"Classificação sugerida pelo modelo: {label} (confiança: {conf_pct})",
            "",
            "Casos similares identificados:",
        ]

        for case in prediction.get("similar_cases", []):
            sim_pct = f"{case['similaridade'] * 100:.0f}%"
            lines.append(
                f"  - Ofensa {case['ofensa_id']} ({case['cliente']}) "
                f"[{case['classificacao']}] similaridade: {sim_pct}"
            )
            if case.get("tipo_alerta"):
                lines.append(f"    Alerta: {case['tipo_alerta']}")

        hints = prediction.get("reasoning_hints", [])
        if hints:
            lines.append("")
            lines.append("Padrões de raciocínio dos casos próximos:")
            for hint in hints[:4]:
                lines.append(f"  • {hint}")

        lines.append("=== Fim do Contexto ML ===")

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars].rstrip() + "\n[... truncado]"
        return result

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _extract_reasoning_hints(self, neighbor_indices: Any) -> list[str]:
        """Extrai frases curtas de raciocínio das seções de pensamento."""
        hints: list[str] = []
        seen: set[str] = set()
        hint_pattern = re.compile(
            r"(?:classific|identific|confirm|descart|evidênc|legitim|malicioso|"
            r"benigno|suspeito|padrão|comportamento|usuário|script|ferrament)[^\n.]{10,90}",
            re.IGNORECASE,
        )
        for idx in neighbor_indices:
            if idx >= len(self._records):
                continue
            rec = self._records[idx]
            for match in hint_pattern.finditer(rec.texto_raciocinio):
                hint = match.group(0).strip()
                normalized = re.sub(r"\s+", " ", hint).lower()
                if normalized not in seen:
                    seen.add(normalized)
                    hints.append(hint)
                if len(hints) >= 6:
                    return hints
        return hints

    # ------------------------------------------------------------------
    # Utilitários públicos
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Retorna status do modelo para diagnóstico."""
        manifest = self._load_manifest()
        return {
            "model_available": self.is_trained(),
            "model_stale": self.is_stale(),
            "training_dir": str(self.training_dir),
            "model_dir": str(self.model_dir),
            "n_samples": manifest.get("n_samples", 0),
            "trained_at": manifest.get("trained_at", ""),
            "label_distribution": manifest.get("label_distribution", {}),
            "model_version": manifest.get("version", ""),
        }

    def list_training_records(self) -> list[dict[str, Any]]:
        """Retorna resumo de todos os casos de treinamento disponíveis."""
        records = self._parser.parse_directory(self.training_dir)
        return [
            {
                "ofensa_id": rec.ofensa_id,
                "cliente": rec.cliente,
                "tipo_alerta": rec.tipo_alerta,
                "classificacao": rec.classificacao,
                "arquivo": rec.arquivo,
            }
            for rec in records
        ]


# ---------------------------------------------------------------------------
# Factory: obtém instância com diretório padrão da instalação do SOCC
# ---------------------------------------------------------------------------

def default_engine(home: Path | None = None) -> TrainingEngine:
    """
    Retorna um TrainingEngine apontando para o diretório Training do projeto SOCC.

    Ordem de resolução:
      1. Variável de ambiente SOCC_TRAINING_DIR (caminho absoluto ou relativo ao CWD)
      2. .agents/Training relativo à raiz do pacote (onde pyproject.toml está)
      3. .agents/Training relativo ao runtime home (~/.socc/...)
    """
    # 1. Variável de ambiente explícita
    env_dir = os.environ.get("SOCC_TRAINING_DIR", "").strip()
    if env_dir:
        training_dir = Path(env_dir).expanduser().resolve()
        model_dir = training_dir.parent / "training_model"
        return TrainingEngine(training_dir=training_dir, model_dir=model_dir)

    # 2. Raiz do pacote: sobe dois níveis a partir de socc/core/training_engine.py
    #    → socc/core/ → socc/ → <projeto>/ → .agents/Training
    package_root = Path(__file__).resolve().parent.parent.parent
    candidate = package_root / ".agents" / "Training"
    if candidate.exists():
        model_dir = package_root / ".agents" / "training_model"
        return TrainingEngine(training_dir=candidate, model_dir=model_dir)

    # 3. Fallback: runtime home (~/.socc/workspace/soc-copilot/Training)
    from socc.cli.installer import runtime_agent_home
    agent_home = runtime_agent_home(home)
    training_dir = agent_home / "Training"
    model_dir = agent_home / "training_model"
    return TrainingEngine(training_dir=training_dir, model_dir=model_dir)


def get_training_context(
    text: str,
    *,
    home: Path | None = None,
    auto_train: bool = True,
    max_chars: int = 1200,
) -> str:
    """
    Ponto de entrada de alto nível para o pipeline de análise.
    Retorna um bloco de texto com a predição ML para injetar no knowledge_context.

    Se o modelo estiver desatualizado e auto_train=True, retreina silenciosamente.
    """
    try:
        engine = default_engine(home)
        if auto_train and engine.is_stale():
            engine.train()
        prediction = engine.predict(text)
        return engine.format_context(prediction, max_chars=max_chars)
    except Exception:
        return ""
