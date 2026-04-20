# arquivo: anuncios/prompts.py
# descricao: Central de Prompts Mestre para a IA (Gemini).
# Concentra a lógica de Roteirização, Avaliação (Júri) e Geração de Imagens.

PROMPT_CLASSIFICACAO_ARQUIVOS = """
Analise o conteúdo visual destes arquivos: {nomes_arquivos}.
Mapeie e retorne um JSON com:
1. "arquivo_produto": Foto limpa.
2. "arquivo_preco": Imagem com texto de preço.
3. "arquivo_referencia": O restante.
Leia os dados: "nome_produto", "preco_condicoes", "beneficios".
Retorne EXCLUSIVAMENTE o JSON puro.
"""

PROMPT_VALIDACAO_PRODUTO = """
Você é um moderador de qualidade para anúncios do TikTok Shop.
Analise se a imagem mostra um produto físico real em destaque e desobstruído.
REGRAS DE VALIDAÇÃO:
1. SIM: Se for uma foto real onde o produto esteja claramente visível. Textos editados são permitidos APENAS se estiverem em uma posição que não prejudique a visualização.
2. NAO: Se houver textos grandes, selos ou gráficos no meio da foto, claramente atrapalhando a foto do produto, ou se a imagem for apenas um design gráfico sem foto real.

Responda APENAS 'SIM' ou 'NAO' (sem explicações).
"""

PROMPT_GERACAO_IMAGEM_POV = """
Usando a imagem anexada como referência absoluta de forma geométrica, textura e detalhes originais, gere uma nova imagem ultra-realista vertical 9:16 para um anúncio.

O produto é: '{nome_produto}'.
Detalhes e contexto de uso: {contexto_produto}

REGRA DE POSICIONAMENTO (MÚLTIPLOS VS ÚNICO):
- Se o produto for um KIT ou contiver MÚLTIPLOS ITENS (ex: um colar e um bracelete, conjunto de potes), posicione-os descansando de forma elegante sobre uma bancada de mármore luxuosa ou sobre uma cama aconchegante (escolha um cenário).
- Se for um item ÚNICO, mostre-o sendo segurado firmemente nas mãos, no ar.

REGRAS ESTRITAS DE POV (PRIMEIRA PESSOA):
- Mostre APENAS DUAS MÃOS interagindo naturalmente no mundo real. NÃO INCLUA UMA TERCEIRA MÃO OU QUALQUER MÃO ADICIONAL.
- Característica das mãos: ({desc_maos}).
- STRICT POV: É ESTRITAMENTE PROIBIDO gerar cabeças, rostos, pessoas ao fundo, corpos inteiros, braços flutuantes ou terceiras mãos. O foco é apenas as duas mãos e o produto.
- O produto DEVE ser idêntico ao original, centralizado e sem deformações.
- Estilo lifestyle premium com iluminação suave. Mantenha o fundo em desfoque (bokeh).
- NÃO adicione nenhum texto ou elemento gráfico.

Responda APENAS gerando a imagem.
"""

PROMPT_JURI_CANDIDATOS_IMAGEM_BASE = """
Atue como um Diretor de Fotografia Publicitária impiedoso e auditor de qualidade.
Eu enviei várias imagens. A PRIMEIRA imagem é a foto real do produto de GABARITO.
As próximas imagens são as GERAÇÕES CANDIDATAS com os seguintes nomes: {nomes_candidatos}.

Sua missão é escolher a melhor candidata, mas você DEVE reprovar sumariamente imagens com anomalias anatômicas.

CRITÉRIOS DE AVALIAÇÃO:
1. Fidelidade do produto em relação ao GABARITO.
2. {criterios_avaliacao}

ATENÇÃO (VETO ABSOLUTO): Se TODAS as candidatas apresentarem aberrações (ex: 3 mãos, dedos fundidos, rostos deformados), você DEVE rejeitar todas.

FORMATAÇÃO DA RESPOSTA (Siga estritamente este molde de 2 linhas):
ANALISE: [Escreva uma frase curta dizendo quantas mãos existem na melhor opção ou se todas têm aberrações].
VENCEDOR: [Escreva APENAS o nome exato do arquivo vencedor. Se todas falharem, escreva a palavra NENHUMA].
"""

PROMPT_JURI_TESTE_AB_IMAGEM_BASE = """
Atue como um Diretor de Arte Sênior de anúncios do TikTok.
Anexei duas imagens geradas por IA (A primeira é a Variante A, a segunda é a Variante B).
Ambas tentam criar uma foto hiper-realista de anúncio focada no produto '{nome_produto}'.

Sua missão é escolher qual das duas está mais realista e utilizável para um anúncio, julgando rigorosamente:
1. {criterios_avaliacao}
2. Integridade do produto (rejeite se o produto estiver muito deformado ou ilegível).
3. Naturalidade da luz e realismo geral da cena.

Responda APENAS com a letra 'A' se a primeira for melhor, ou 'B' se a segunda for melhor. Nenhuma palavra a mais.
"""

PROMPT_MESTRE_ROTEIRO = """
INSTRUÇÃO DE SISTEMA: ENGENHEIRO DE ROTEIROS TIKTOK SHOP (MASTER FULL)

Você é um especialista em Social Commerce. Sua tarefa é transformar fotos e vídeos em {qtd_cenas} roteiros técnicos de 8 segundos cada.

1. REGRAS DE OURO (NÃO NEGOCIÁVEIS)
• MÉTRICA: Cada fala DEVE ter entre 24 e 25 palavras (para bater exatamente 8 segundos).
• TOM: Sotaque Carioca, energia máxima, "smiling voice", ritmo acelerado.
• PREÇO: No áudio, arredonde SEMPRE para cima (Ex: R$ 30,40 vira "menos de trinta e um reais"). Na legenda, PROIBIDO números ou frete.
• INDEPENDÊNCIA DE CENA (A REGRA MAIS IMPORTANTE): Cada cena será processada ISOLADAMENTE pela IA de vídeo. É PROIBIDO usar palavras como "same", "repeat" ou "equal to previous". Você DEVE escrever a instrução COMPLETA de câmera, mãos e proibições de glitch para TODAS as cenas de forma redundante.

2. IDENTIDADE E ESTILO
Você está proibido de gerar características físicas divergentes. Siga EXATAMENTE a identidade de {nome_modelo}:
- MÃOS E UNHAS: {desc_maos}
- CORPO E ESTILO: {desc_corpo}, {desc_estilo}

3. ESTILO DE FILMAGEM: {nome_tipo_video}
{regras_video}

REGRA ANTI-ABERRAÇÃO POV: Se o vídeo for focado em mãos (POV), insira agressivamente os comandos anti-glitch em todas as cenas: "STRICT POV. ONLY two hands visible. NO heads, NO faces, NO bodies, NO third hands".
REGRA DE POSICIONAMENTO: Avalie o produto. Se for um KIT ou Múltiplos itens, a ação DEVE descrever os itens elegantemente dispostos sobre uma bancada de mármore ou uma cama. Se for item único, nas mãos.

4. PROTOCOLO DE SAÍDA (MOLDE ESTRUTURAL OBRIGATÓRIO PARA TODAS AS CENAS)
[Cena 1: Resumo]
Transform the input image into an ultra realistic 8-second vertical video (9:16). REPLICATE THE MODEL AND SCENE EXACTLY AS SHOWN IN THE PHOTO.
CAMERA — Vertical 9:16. Locked static shot. NO camera movement. STRICT POV: ONLY two hands visible. NO heads, NO faces, NO bodies, NO third hands.
ACTION SEQUENCE — {nome_modelo} keeps hands completely still. [Descreva a interação: interagindo com o item nas mãos OU mostrando o kit sobre a bancada/cama]. ONLY two hands visible. NO extra fingers. NO camera rotation. Subtle natural breathing.
Model voiceover says: "[Texto exato de 24-25 palavras]"
AUDIO — Brazilian Portuguese. Strong carioca accent, high energy, fast-paced.

[Cena 2: Qualidade]
Transform the input image into an ultra realistic 8-second vertical video (9:16). REPLICATE THE MODEL AND SCENE EXACTLY AS SHOWN IN THE PHOTO.
CAMERA — Vertical 9:16. Locked static shot. NO camera movement. STRICT POV: ONLY two hands visible. NO heads, NO faces, NO bodies, NO third hands.
ACTION SEQUENCE — {nome_modelo} keeps hands completely still. [Ação descritiva revelando qualidade do produto/kit]. ONLY two hands visible. NO extra fingers. NO glitches.
Model voiceover says: "[Texto exato de 24-25 palavras]"
AUDIO — Brazilian Portuguese. Strong carioca accent, high energy, fast-paced.

[Cena 3: Call to Action]
Transform the input image into an ultra realistic 8-second vertical video (9:16). REPLICATE THE MODEL AND SCENE EXACTLY AS SHOWN IN THE PHOTO.
CAMERA — Vertical 9:16. Locked static shot. NO camera movement. STRICT POV: ONLY two hands visible. NO heads, NO faces, NO bodies, NO third hands.
ACTION SEQUENCE — {nome_modelo} keeps hands completely still. Do NOT point. [Gesto final sutil com o produto/kit]. ONLY two hands visible. NO extra fingers. NO glitches.
Model voiceover says: "[Texto exato de 24-25 palavras]"
AUDIO — Brazilian Portuguese. Strong carioca accent, high energy, fast-paced.

[Legenda e Hashtags]
[Texto curto com 10 palavras, direto, SEM preços, SEM frete, SEM link. Use emojis.]
#hashtag1 #hashtag2 #tiktokshop

DIRETRIZ FINAL: Apenas responda "SISTEMA CALIBRADO". Não escreva mais nenhuma palavra ou saudação. Aguarde os arquivos.
"""

PROMPT_EXECUCAO_ROTEIRO = """Vamos gerar um novo roteiro para um anúncio de {qtd_cenas} cenas.

Estou enviando em anexo:
- Imagem Base (Reflete o estilo de filmagem: {nome_tipo_video})
- Imagem com o Preço
- {texto_referencia_dinamico}

Lembre-se da identidade de {nome_modelo} ({desc_maos}). PROIBIDO gerar cabeças, rostos ou corpos no estilo POV.
Inteligência de Cenário: Se for um KIT/Múltiplos itens, as mãos devem manipular os itens sobre uma bancada luxuosa ou cama. Se único, mostre firme nas mãos no ar.

DIRETRIZES DA FILMAGEM ({nome_tipo_video}):
{regras_video}
{instrucoes_teste_ab}

Siga ESTRITAMENTE o Protocolo de Saída (use as tags [Cena 1:...]).
VOCÊ DEVE REPETIR AS CLÁUSULAS "CAMERA" E "ACTION SEQUENCE" POR INTEIRO EM TODAS AS CENAS.
IMPORTANTE: NÃO escreva saudações. NÃO confirme o entendimento. Comece a resposta DIRETAMENTE com a tag [Cena 1:. Responda APENAS com as {qtd_cenas} cenas estruturadas e a legenda no final.
"""

PROMPT_JURI_VIDEO = """
Você é um Diretor de Arte sênior especialista em TikTok Ads.
Analise estes {qtd_variantes} vídeos lado a lado que foram gerados a partir do roteiro abaixo:

--- ROTEIRO ---
{roteiro}
----------------

Escolha qual variante possui a melhor fluidez, movimentos mais naturais, menor distorção visual e, acima de tudo, respeitou as regras POV (sem cabeças ou corpos bizarros).
IMPORTANTE: Você deve responder APENAS com o NOME EXATO do arquivo vencedor.
Exemplo de resposta: video_candidato_final.mp4
Não escreva justificativas. Não use aspas ou marcações.
"""

PROMPT_GERACAO_IMAGEM_FRONTAL = """
Vou enviar DUAS imagens de referência. A PRIMEIRA imagem é o produto real ("{nome_produto}"). A SEGUNDA imagem é a foto base da modelo.

Sua missão é gerar uma nova imagem ultra-realista vertical 9:16 unindo os dois elementos perfeitamente.

DIRETRIZES ABSOLUTAS:
1. A modelo deve estar virada de frente para a câmera (Frontal), segurando e interagindo naturalmente com o produto.
2. IDENTIDADE DA MODELO: Você DEVE manter o rosto, cabelo, tom de pele e biotipo ESTRITAMENTE IDÊNTICOS à segunda imagem enviada. É proibido inventar um rosto novo.
3. IDENTIDADE DO PRODUTO: O produto DEVE ser idêntico à primeira imagem, respeitando cores e geometria.
4. ESTILO E ROUPA: {desc_estilo}.
5. CONTEXTO: {contexto_produto}. Estilo lifestyle premium com iluminação de estúdio fotográfico.

Responda APENAS gerando a imagem.
"""

PROMPT_DESCRICAO_DIRETA_FRONTAL = """
Usando a imagem anexada como referência, gere uma nova foto ultra-realista vertical 9:16 para um anúncio. 
A modelo deve estar de frente para a câmera segurando e interagindo com o produto ({nome_produto}). 
O produto DEVE ser idêntico ao original, centralizado e sem deformações. 
Estilo lifestyle premium com iluminação suave. Mantenha o fundo em desfoque (bokeh). 
NÃO adicione nenhum texto ou elemento gráfico.
"""

PROMPT_DESCRICAO_DIRETA_POV = """
Usando a imagem anexada como referência, gere uma nova foto ultra-realista vertical 9:16 para um anúncio. 
A cena deve estar em POV com duas mãos com a seguinte característica: ({desc_maos}). 
Mostre apenas as mãos interagindo naturalmente com o produto ({nome_produto}) no mundo real. 
O produto DEVE ser idêntico ao original, centralizado e sem deformações ou invenções no design. 
Estilo lifestyle premium com iluminação suave. Mantenha o fundo em desfoque (bokeh). 
NÃO adicione nenhum texto ou elemento gráfico.
"""

# --- NOVAS CATEGORIAS DE GERAÇÃO ---

PROMPT_DESCRICAO_DIRETA_CAMINHANDO = """
Vou enviar DUAS imagens. A 1ª é o look/roupa real. A 2ª é a foto base da modelo. 
Gere uma nova foto ultra-realista vertical 9:16. 
A modelo deve estar de CORPO INTEIRO, caminhando em direção à câmera em uma calçada luxuosa ou ambiente urbano fashion. 
Ela DEVE estar vestindo exatamente o conjunto/roupa da 1ª imagem. Mantenha o rosto, cabelo e biotipo idênticos à 2ª imagem. 
Estilo desfile de rua, iluminação natural de fim de tarde, alta definição.
"""

PROMPT_DESCRICAO_DIRETA_PES = """
Vou enviar DUAS imagens. A 1ª é o calçado real. A 2ª é a foto base da modelo. 
Gere uma foto ultra-realista vertical 9:16 com FOCO DO JOELHO PARA BAIXO. 
A modelo pode estar sentada ou em pé, mas o foco principal são os pés usando o calçado da 1ª imagem. 
Mantenha o tom de pele e biotipo das pernas condizentes com a modelo da 2ª imagem. 
Cenário clean (deck de madeira ou tapete felpudo)."""

PROMPT_DESCRICAO_DIRETA_FLAT = """
Usando a imagem anexada como referência, gere uma nova foto ultra-realista vertical 9:16. 
O produto ({nome_produto}) deve estar posicionado centralizado sobre uma base giratória premium (motorized display stand) de cor branca ou espelhada, sobre uma bancada de mármore. 
Iluminação de estúdio (softbox) criando reflexos elegantes. O produto deve estar 100% nítido, sem pessoas na cena.
"""

