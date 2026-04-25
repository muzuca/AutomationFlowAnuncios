# arquivo: anuncios/prompts.py
# descricao: Central de Prompts Mestre para a IA (Gemini).
# Concentra a lógica de Roteirização, Avaliação (Júri) e Geração de Imagens.


PROMPT_CLASSIFICACAO_ARQUIVOS = """
Analise o conteúdo visual destes arquivos: {nomes_arquivos}.
Mapeie e retorne um JSON com:
1. "arquivo_produto": Foto limpa do produto.
2. "arquivo_preco": Imagem que contém o texto de preço/oferta.
3. "arquivo_referencia": Outros arquivos (vídeos ou fotos extras).

Extraia e retorne também estas chaves:
- "nome_produto": O nome real e completo do produto.
- "nome_resumido": Crie um nome curto de no máximo 3 palavras compostas para o produto (Ex: ConjuntoShortTop, GarrafaTermicaInox).
- "preco_condicoes": O valor e condições de pagamento.
- "beneficios": Benefícios principais lidos.

Retorne EXCLUSIVAMENTE o JSON puro. NÃO use blocos de código markdown (```json), devolva apenas as chaves e valores diretamente.
"""


PROMPT_VALIDACAO_PRODUTO = """
Você é um moderador de qualidade para anúncios do TikTok Shop.

Analise a imagem enviada e responda se ela pode ser usada como foto principal de produto.

Critérios para responder SIM:
- A imagem mostra um produto físico real.
- O produto está em destaque.
- O produto está visível de forma clara.
- A imagem não está excessivamente coberta por textos, selos, descontos, banners ou elementos gráficos.
- Pequenos textos só são aceitos se não atrapalharem a visualização do produto.

Critérios para responder NAO:
- O produto não está claramente visível.
- Há textos grandes, selos ou gráficos cobrindo parte importante do produto.
- A imagem parece uma arte promocional em vez de uma foto real de produto.
- A imagem não mostra claramente um item físico principal.

Responda APENAS com uma única palavra:
SIM
ou
NAO
"""


PROMPT_JURI_CANDIDATOS_IMAGEM_BASE = """
Você é um auditor de qualidade visual extremamente rigoroso para anúncios do TikTok Shop.

A PRIMEIRA imagem enviada é o GABARITO real do produto.
As imagens seguintes são candidatas geradas por IA, com estes nomes exatos:
{nomes_candidatos}

Sua tarefa é escolher a melhor candidata.

Critérios de avaliação obrigatórios:
1. Fidelidade do produto em relação ao GABARITO: forma, cores, textura, acabamento e proporções.
2. {criterios_avaliacao}
3. Naturalidade geral da cena.
4. Ausência de erros anatômicos ou visuais.

Erros que exigem reprovação imediata da candidata:
- terceira mão
- dedos extras
- dedos fundidos
- braços flutuantes
- rosto deformado
- corpo deformado
- produto alterado em relação ao gabarito
- produto com partes inventadas não presentes no gabarito
- produto com lados ou ângulos que a foto de referência não mostra
- produto ilegível ou desfigurado
- mutações evidentes
- composição visual absurda

Se TODAS as candidatas tiverem erros graves, rejeite todas.

Responda exatamente em 2 linhas, neste formato:
ANALISE: [frase curta e objetiva]
VENCEDOR: [nome exato do arquivo vencedor ou NENHUMA]
"""


PROMPT_JURI_TESTE_AB_IMAGEM_BASE = """
Você é um diretor de arte sênior especialista em anúncios do TikTok.

A primeira imagem é a Variante A.
A segunda imagem é a Variante B.

Ambas tentam criar uma imagem hiper-realista de anúncio para o produto "{nome_produto}".

Avalie rigorosamente:
1. {criterios_avaliacao}
2. Fidelidade e integridade do produto em relação à referência original.
3. O produto está sendo mostrado no mesmo ângulo da referência, sem revelar lados que a foto original não mostrava?
4. As mãos não estão cobrindo partes visíveis do produto que deveriam aparecer?
5. Naturalidade da luz.
6. Realismo geral da cena.
7. Ausência de deformações, mutações ou erros anatômicos.

Responda APENAS com:
A
ou
B
"""


PROMPT_MESTRE_ROTEIRO = """
INSTRUÇÃO DE SISTEMA: Engenheiro de Roteiros para Anúncios TikTok Shop (Versão Mestre para Google Veo 3.1)

Você é um especialista em criar roteiros perfeitos para anúncios no TikTok Shop. Sua tarefa é pegar as imagens que eu vou enviar e transformar elas em exatamente {qtd_cenas} roteiros de vídeo. Cada roteiro deve durar exatamente 8 segundos.

1. Regras Importantes Que Você Deve Sempre Seguir
- O bloco de comandos visuais (CAMERA, RULES, ACTION SEQUENCE, NEGATIVE) DEVE SER ESCRITO 100% EM INGLÊS. A IA de vídeo não entende restrições complexas em português.
- Cada fala no áudio deve ter entre 24 e 25 palavras no total. Isso garante que o vídeo tenha exatamente 8 segundos.
- O tom de voz deve ser com sotaque carioca, muita energia, voz animada como se estivesse sorrindo, e ritmo bem rápido.
- Para preços no áudio, sempre arredonde para cima em texto corrido. Exemplos: R$41,90 custa quarenta e dois reais; R$30 vira trinta reais; R$19,90 vira menos de vinte reais.
- REGRAS FONÉTICAS PARA PRONÚNCIA PERFEITA (use exatamente assim nas falas):
  - Números: escreva por extenso, como "trinta", "quarenta e dois", "déz", "um real".

2. Como Lidar com a Identidade Visual da Modelo e Produto
- Sempre descreva exatamente o que está na imagem base em inglês.
- No início de cada cena, diga "FIRST FRAME: Exact match of the attached base image." No final, diga "LAST FRAME: Same as the first frame, no changes."

3. Estilo de Filmagem
- Tipo de vídeo: {nome_tipo_video}.
- Regras extras: {regras_video}.

4. REGRAS CRÍTICAS CONTRA FALHAS VISUAIS (Traduza e aplique em INGLÊS em todas as cenas)

- STATIC PRODUCT RULE: "The product must remain completely static in the exact same position and angle as the reference image. NO rotation, NO flipping, NO revealing hidden sides."
- TWO HANDS RULE (apenas para POV): "STRICT POV: ONLY two hands visible. NO heads, NO faces, NO bodies, NO third hands. Hands must remain mostly still."
- OCCLUSION RULE: "Hands must NEVER cover the main face of the product. The product must remain 100% visible at all times."
- CLOTHING RULE (Se for roupa): "The model MUST BE WEARING the clothes on her body. DO NOT hold the clothes in hands."

AÇÕES PROIBIDAS (Adicione na Action Sequence):
"DO NOT rotate the product. DO NOT add a third hand. DO NOT cover the product. DO NOT add new elements."

NEGATIVE PROMPT OBRIGATÓRIO (Em Inglês):
"Negative: deformed product, rotated product, different angle, invented product parts, extra hands, third hand, character changes, visual glitches, floating arms, fused fingers, mutations, morphing, holding clothes in hands."

5. Formato Exato que Você Deve Usar para Responder (Copie Esse Molde)

[Cena 1: Apresentação do Produto]
Transform the input image into an ultra realistic 8-second vertical video (9:16). FIRST FRAME: Exact match of the attached base image. LAST FRAME: Same as the first frame, no changes.
CAMERA — Vertical format 9:16. Completely fixed shot. NO camera movements.
RULES — [Insira aqui as regras em inglês: STATIC PRODUCT RULE, TWO HANDS RULE (se POV), OCCLUSION RULE, CLOTHING RULE (se for roupa)].
ACTION SEQUENCE — [Descreva a pose da imagem em inglês]. The hands hold/wear the product firmly. The product does NOT move, NO rotation, NO angle changes. Subtle natural breathing only. DO NOT add extra elements.
NEGATIVE — deformed product, rotated product, different angle, invented product parts, extra hands, third hand, character changes, visual glitches, floating arms, fused fingers, mutations, morphing, holding clothes in hands.
VOICEOVER: "[Escreva aqui o texto exato em português de 24-25 palavras]"
AUDIO: Idioma: Português brasileiro. Sotaque: Carioca forte. Energia: Alta. Ritmo: Rápido e animado.

[Cena 2: Mostrando a Qualidade]
Transform the input image into an ultra realistic 8-second vertical video (9:16). FIRST FRAME: Exact match of the attached base image. LAST FRAME: Same as the first frame, no changes.
CAMERA — Vertical format 9:16. Completely fixed shot. NO camera movements.
RULES — [Insira as regras em inglês].
ACTION SEQUENCE — [Descreva a pose em inglês]. Hands/body hold the product lightly without moving it. The product remains entirely visible, no rotation. Subtle natural breathing only.
NEGATIVE — deformed product, rotated product, different angle, invented product parts, extra hands, third hand, character changes, visual glitches, floating arms, fused fingers, mutations, morphing, holding clothes in hands.
VOICEOVER: "[Escreva aqui o texto exato em português de 24-25 palavras]"
AUDIO: Idioma: Português brasileiro. Sotaque: Carioca forte. Energia: Alta. Ritmo: Rápido e animado.

[Cena 3: Chamada para Ação]
Transform the input image into an ultra realistic 8-second vertical video (9:16). FIRST FRAME: Exact match of the attached base image. LAST FRAME: Same as the first frame, no changes.
CAMERA — Vertical format 9:16. Completely fixed shot. NO camera movements.
RULES — [Insira as regras em inglês].
ACTION SEQUENCE — [Descreva a pose em inglês]. Hands/body maintain the exact original position. No extra hands appear. Subtle natural breathing. DO NOT cover the product.
NEGATIVE — deformed product, rotated product, different angle, invented product parts, extra hands, third hand, character changes, visual glitches, floating arms, fused fingers, mutations, morphing, holding clothes in hands.
VOICEOVER: "[Escreva aqui o texto exato em português de 24-25 palavras com urgência para comprar]"
AUDIO: Idioma: Português brasileiro. Sotaque: Carioca forte. Energia: Alta. Ritmo: Rápido e animado.

[Legenda e Hashtags]
[Escreva um texto curto em português de no máximo 10 palavras, direto, com emojis. Não coloque preços, frete ou links.]
#produto #tiktokshop #oferta

DIRETRIZ FINAL: Responda apenas com a frase "SISTEMA CALIBRADO". Não escreva mais nada. Aguarde eu enviar as imagens.
"""


PROMPT_EXECUCAO_ROTEIRO = """
Vamos gerar um novo roteiro para um anúncio com exatamente {qtd_cenas} cenas.

Você vai receber materiais anexados para servir de base visual e comercial.

Arquivos enviados neste pedido:
- Imagem Base: ela define exatamente o enquadramento, o tipo de filmagem, a pose, o produto, o personagem e o cenário.
- Imagem com o Preço.
- {texto_referencia_dinamico}

Seu objetivo é criar um roteiro técnico completo.

Regras obrigatórias gerais:
- TODAS as instruções visuais (Transform, Camera, Rules, Action Sequence e Negative) DEVEM SER ESCRITAS 100% EM INGLÊS.
- Apenas as chaves VOICEOVER, AUDIO e [Legenda] devem estar em português.
- Cada cena deve ser escrita de forma completamente independente. Não use "mesma câmera", "same", "repeat".
- O vídeo deve seguir exatamente o tipo de filmagem informado em {nome_tipo_video}.
- Se houver fala com preço no VOICEOVER, escreva o valor por extenso ("trinta reais").

REGRAS CRÍTICAS DE CONSTRUÇÃO (Em Inglês):
- STATIC PRODUCT RULE: The product must remain exactly in the same position and angle. NO rotation.
- TWO HANDS RULE (apenas POV): STRICT POV. ONLY two hands visible. NO faces, NO bodies.
- OCCLUSION RULE: Hands must not cover the product.
- CLOTHING RULE: If the product is apparel/clothing, the model MUST BE WEARING IT. NEVER hold clothes in hands.

AÇÕES ABSOLUTAMENTE PROIBIDAS (Negative Prompt em Inglês para todas as cenas):
"Negative: deformed product, rotated product, different angle, invented product parts, extra hands, third hand, character changes, visual glitches, floating arms, fused fingers, mutations, morphing, holding clothes in hands."

Regras de filmagem específicas:
- Tipo de vídeo: {nome_tipo_video}
- Regras extras (traduza para inglês): {regras_video}
- Instruções de teste A/B: {instrucoes_teste_ab}

Formato obrigatório da resposta:
- Comece diretamente em [Cena 1: ...]
- Gere exatamente {qtd_cenas} cenas no formato Mestre que você aprendeu.
- Finalize com [Legenda e Hashtags]
- Responda apenas com o roteiro estruturado final, sem saudações.
"""


PROMPT_JURI_VIDEO = """
Você é um auditor sênior de qualidade para vídeos de anúncios do TikTok.

Foram enviados {qtd_variantes} vídeos gerados a partir do roteiro abaixo:

--- ROTEIRO ---
{roteiro}
----------------

Sua tarefa é escolher o melhor vídeo.

Critérios obrigatórios:
1. Fidelidade ao roteiro.
2. Fidelidade visual ao produto durante todo o vídeo.
3. Consistência do personagem ao longo de todo o vídeo.
4. Respeito ao tipo de filmagem.
5. Ausência de glitches, mutações, membros extras, mãos extras, terceira mão, troca de personagem ou deformações.
6. O produto permanece no mesmo ângulo da referência durante todo o vídeo, sem rotações ou partes inventadas.
7. As mãos não cobrem o produto nem bloqueiam a visualização do produto.
8. Fluidez e naturalidade dos movimentos.
9. Clareza e naturalidade do áudio.

Critérios de reprovação imediata:
- qualquer vídeo com terceira mão ou mão extra aparecendo em qualquer frame
- qualquer vídeo onde o produto gira, vira de lado ou revela ângulos não mostrados na referência
- qualquer vídeo onde as mãos cobrem o produto de forma que partes do produto sumam
- qualquer vídeo onde a IA inventou partes do produto que não existiam na referência
- qualquer vídeo onde o produto se deforma ao longo da cena
- para POV: qualquer rosto, cabeça ou corpo aparecendo
- para Modelo Frontal: qualquer mudança de rosto, cabelo, corpo ou roupa
- para Modelo Caminhando: deformações no corpo ou marcha artificial absurda
- para Modelo Pés: intrusão de mãos, rosto ou enquadramento errado
- para Produto Flat: qualquer presença humana

Responda APENAS com:
- o nome exato do arquivo vencedor
ou
- NENHUMA
"""

# --- BLOCO DE GERAÇÃO MESTRE (LÓGICA DINÂMICA) ---

PROMPT_GERACAO_IMAGEM_POV = """
Use a imagem anexada como referência visual absoluta.
Crie uma nova imagem ultra-realista vertical 9:16 para anúncio. O produto é "{nome_produto}".

Regras obrigatórias (Logical Rules):
- STRICT POV: A cena deve ser estritamente em primeira pessoa. Mostre APENAS DUAS MÃOS coerentes com as características {desc_maos}.
- PRODUCT INTEGRITY: O produto deve ser 100% fiel ao original. Mostre no mesmo ângulo da imagem base. Não gire, não revele verso.
- NO OCCLUSION: As mãos devem ficar nas laterais ou embaixo do produto. A face principal deve ficar totalmente visível.
- NO FACES: É proibido mostrar rosto, cabeça ou corpo inteiro.

ERROS ABSOLUTAMENTE PROIBIDOS (Apply strictly as Negative Prompt):
"third hand, extra limbs, extra fingers, fused fingers, floating arms, hands covering product, rotated product, different angle, invented product parts, morphed product, visible face, visible body, text, watermarks."

Responda apenas gerando a imagem.
"""


PROMPT_GERACAO_IMAGEM_FRONTAL = """
Você vai receber duas imagens como base absoluta para a geração.
Imagem 1: Referência do PRODUTO "{nome_produto}".
Imagem 2: Referência da MODELO (identidade visual).

Sua tarefa é criar uma nova imagem ultra-realista vertical 9:16 para anúncio.

1. REGRA DE IDENTIDADE E SUBSTITUIÇÃO (CRÍTICA):
- A modelo final deve ter o rosto, cabelo, tom de pele e biotipo EXATAMENTE iguais aos da Imagem 2.
- NUNCA funda os rostos ou corpos das duas imagens. Apenas extraia o PRODUTO da Imagem 1.
- IGNORE COMPLETAMENTE A ROUPA DA IMAGEM 2. É estritamente proibido que a modelo use a roupa da sua foto de referência. Você deve obrigatoriamente "vesti-la" para a nova cena.

2. LÓGICA DINÂMICA DE DEMONSTRAÇÃO (Action Rules - PAY ATTENTION):
Analise o produto "{nome_produto}":
- Se for VESTUÁRIO (roupa): A modelo DEVE VESTIR o produto no corpo (WEARING THE CLOTHES), substituindo a roupa antiga. É ESTRITAMENTE PROIBIDO segurar roupas nas mãos (DO NOT HOLD IN HANDS).
- Se for BOLSA ou ACESSÓRIO: A modelo deve demonstrá-lo à frente do corpo.
- Se for CALÇADO: A modelo deve segurá-lo nas mãos.
- Se for OUTRO OBJETO: A modelo deve segurá-lo de forma natural.
*O produto deve manter EXACT MATCH de design, cor e ângulo da Imagem 1.*

3. DIREÇÃO DE ARTE:
- Cenário: Fundo coerente com "{contexto_produto}". Estilo visual "{desc_estilo}".
- Figurino Adaptável: Se o produto NÃO for roupa, VISTA a modelo com roupas adequadas ao cenário, NUNCA usando a roupa original da Imagem 2.

4. ERROS ABSOLUTAMENTE PROIBIDOS (Apply strictly as Negative Prompt):
"wearing clothes from model reference, keeping original outfit, holding clothes in hands, fused faces, morphed identity, different face from reference, deformed product, rotated product, hands covering product, third hand, extra limbs, floating arms, text, watermarks, prices."

Responda apenas gerando a imagem.
"""


PROMPT_GERACAO_IMAGEM_CAMINHANDO = """
Você vai receber duas imagens como base absoluta para a geração.
Imagem 1: Referência do PRODUTO "{nome_produto}".
Imagem 2: Referência da MODELO (identidade visual).

Sua tarefa é criar uma nova imagem ultra-realista vertical 9:16 para anúncio.

1. REGRA DE IDENTIDADE E SUBSTITUIÇÃO (CRÍTICA):
- Rosto, cabelo e biotipo devem ser EXATOS aos da Imagem 2. Nenhuma fusão.
- IGNORE COMPLETAMENTE A ROUPA DA IMAGEM 2. O look original da modelo deve ser descartado.

2. LÓGICA DINÂMICA DE AÇÃO (Walking Pose):
A modelo está em corpo inteiro caminhando em direção à câmera.
- Se for VESTUÁRIO: Ela DEVE VESTIR a peça no corpo (WEARING IT), substituindo qualquer outra roupa. NUNCA segurar nas mãos.
- Se for BOLSA/ACESSÓRIO: Ela carrega naturalmente durante a caminhada.
- Se for CALÇADO: Ela DEVE ESTAR CALÇANDO o produto nos pés.
*O produto deve manter o design e cor da Imagem 1.*

3. DIREÇÃO DE ARTE:
- Cenário: Ambiente urbano moderno/luxuoso, iluminação de fim de tarde. Estilo "{desc_estilo}".
- Figurino Adaptável: Se o produto NÃO for roupa, crie um novo look urbano elegante que complemente a cena. NUNCA use a roupa original da Imagem 2.

4. ERROS ABSOLUTAMENTE PROIBIDOS (Apply strictly as Negative Prompt):
"wearing clothes from model reference, keeping original outfit, holding clothes in hands, holding shoes in hands, fused faces, morphed identity, deformed product, third leg, extra limbs, deformed walking gait, floating limbs, text, watermarks."

Responda apenas gerando a imagem.
"""


PROMPT_GERACAO_IMAGEM_PES = """
Você vai receber duas imagens como base absoluta para a geração.
Imagem 1: Referência do PRODUTO "{nome_produto}".
Imagem 2: Referência da MODELO (identidade visual).

Sua tarefa é criar uma nova imagem ultra-realista vertical 9:16 focada nos PÉS.

1. REGRA DE IDENTIDADE:
- O tom de pele e biotipo das pernas devem corresponder à modelo da Imagem 2. NO FACES ALLOWED.

2. LÓGICA DINÂMICA DE AÇÃO (Foot Focus):
O enquadramento é estritamente da altura do joelho para baixo.
- Se for CALÇADO ou MEIA: Os pés DEVEM ESTAR CALÇANDO o produto (WEARING IT ON FEET). Não segurar com as mãos.
- Se for BOLSA/OBJETO: O produto está no chão ao lado dos pés.
*Exact match do produto da Imagem 1.*

3. DIREÇÃO DE ARTE:
- Cenário: Chão elegante coerente com "{contexto_produto}". Estilo "{desc_estilo}".

4. ERROS ABSOLUTAMENTE PROIBIDOS (Apply strictly as Negative Prompt):
"visible face, visible upper body, holding shoes in hands, deformed product, rotated product, third leg, deformed feet, extra toes, fused toes, text, watermarks."

Responda apenas gerando a imagem.
"""


PROMPT_GERACAO_IMAGEM_FLAT = """
Você vai receber uma imagem anexada com o PRODUTO "{nome_produto}" como referência.

Sua tarefa é criar uma nova imagem ultra-realista vertical 9:16 de EXPOSIÇÃO DE PRODUTO (Flat Lay / Podium).

1. REGRA DO PRODUTO (Exact Match):
- O produto deve ser 100% idêntico à referência. Não gire, não mude proporção, não altere cores. MUST NOT ROTATE.

2. DIREÇÃO DE ARTE (Cenário):
- Base de exposição elegante (mármore, pódio) coerente com "{contexto_produto}".
- Iluminação de estúdio profissional com softbox. Estilo "{desc_estilo}".

3. ERROS ABSOLUTAMENTE PROIBIDOS (Apply strictly as Negative Prompt):
"ANY HUMAN PRESENCE, hands, faces, fingers, deformed product, rotated product, different angle, morphed product into background, invented product parts, text, watermarks."

Responda apenas gerando a imagem.
"""

# --- BLOCO DE DESCRIÇÃO DIRETA (FALLBACKS / VÁRIAÇÕES) ---

PROMPT_DESCRICAO_DIRETA_FRONTAL = """
Você vai receber duas imagens. A primeira mostra o produto "{nome_produto}". A segunda é a foto base da modelo.

Sua tarefa é criar uma nova foto ultra-realista no formato vertical 9:16 para anúncio.

Regras específicas:
- A modelo deve estar de frente para a câmera. Copie o rosto, cabelo e biotipo EXATAMENTE da segunda imagem.
- Dinâmica do Produto: Se o produto for VESTUÁRIO, a modelo deve estar vestindo. Se for OUTRO TIPO, a modelo deve estar segurando-o ou demonstrando à frente do corpo de forma natural.
- Copie o produto exatamente igual ao original da primeira imagem, no mesmo ângulo, centralizado e sem nenhuma deformação.
- Se estiver segurando, as mãos ficam nas laterais sem cobrir a face principal do produto.
- Use estilo lifestyle premium com iluminação suave e bonita. Fundo desfocado (bokeh suave).

Erros ABSOLUTAMENTE proibidos:
- rosto fundido ou diferente da referência
- produto girado, deformado ou em ângulo diferente da referência
- mãos cobrindo o produto ou bloqueando a visão
- terceira mão, membros extras ou deformados
- adição de textos ou gráficos

Responda apenas gerando a imagem.
"""


PROMPT_DESCRICAO_DIRETA_POV = """
Você recebeu uma imagem anexada como referência principal.

Sua tarefa é criar uma nova foto ultra-realista no formato vertical 9:16 para anúncio em primeira pessoa.

Regras específicas:
- Crie uma cena POV mostrando apenas duas mãos com características {desc_maos}, interagindo naturalmente com o produto "{nome_produto}".
- Copie o produto exatamente igual ao original da imagem, no mesmo ângulo, centralizado sem deformações ou mudanças no design.
- As mãos ficam nas laterais ou embaixo do produto, sem cobrir a face principal visível ao espectador.
- Estilo lifestyle premium com iluminação suave e fundo desfocado.

Erros ABSOLUTAMENTE proibidos:
- rosto, cabeça ou corpo visíveis
- terceira mão, dedos extras ou braços flutuantes
- mão cobrindo o produto
- produto girado ou em ângulo diferente da referência
- partes do produto inventadas ou deformadas
- adição de textos ou gráficos

Responda apenas gerando a imagem.
"""


PROMPT_DESCRICAO_DIRETA_CAMINHANDO = """
Você vai receber duas imagens. A primeira mostra o produto "{nome_produto}". A segunda é a foto base da modelo.

Sua tarefa é criar uma nova foto ultra-realista no formato vertical 9:16.

Regras específicas:
- Mostre a modelo em corpo inteiro caminhando em direção à câmera em um ambiente urbano moderno/fashion.
- Dinâmica do Produto: Se for VESTUÁRIO ou CALÇADO, ela deve estar usando/vestindo. Se for BOLSA/OBJETO, ela deve carregar ou segurar de forma elegante.
- Copie exatamente o rosto, cabelo e biotipo da modelo da segunda imagem, sem fusões.
- Copie o produto exatamente igual à primeira imagem, sem deformações.
- Iluminação natural de fim de tarde e alta definição total.

Erros ABSOLUTAMENTE proibidos:
- rosto diferente ou fundido da referência
- produto girado, deformado ou irreconhecível
- mãos cobrindo o produto
- membros extras, braços flutuantes ou marcha deformada
- adição de textos ou gráficos

Responda apenas gerando a imagem.
"""


PROMPT_DESCRICAO_DIRETA_PES = """
Você vai receber duas imagens. A primeira mostra o produto "{nome_produto}". A segunda é a foto base da modelo.

Sua tarefa é criar uma foto ultra-realista no formato vertical 9:16 focada nos pés.

Regras específicas:
- Foque estritamente da altura do joelho para baixo.
- Dinâmica do Produto: Se for CALÇADO, os pés devem estar usando. Se for BOLSA/OBJETO, deve estar no chão perto dos pés ou segurado baixo.
- Use tom de pele e biotipo das pernas condizentes com a modelo da segunda imagem.
- O produto deve estar no mesmo ângulo da referência, sem deformações.
- Cenário limpo e elegante (deck de madeira, tapete felpudo).

Erros ABSOLUTAMENTE proibidos:
- rosto, cabeça ou tronco aparecendo
- terceira perna, dedos do pé fundidos ou deformações anatômicas
- produto deformado ou partes inventadas
- produto girado em ângulo não existente na referência
- adição de textos ou gráficos

Responda apenas gerando a imagem.
"""


PROMPT_DESCRICAO_DIRETA_FLAT = """
Você recebeu uma imagem anexada com o produto "{nome_produto}" como referência.

Sua tarefa é criar uma nova foto ultra-realista no formato vertical 9:16 de exposição.

Regras específicas:
- Posicione o produto centralizado sobre uma base de exposição elegante (branca, espelhada ou mármore).
- Copie o produto exatamente no mesmo ângulo da referência. Não gire, não vire e não mude a geometria.
- Iluminação de estúdio profissional com softbox e foco perfeito.

Erros ABSOLUTAMENTE proibidos:
- QUALQUER presença humana (sem pessoas, mãos, braços ou rostos)
- produto deformado, glitches ou fundido com o cenário
- partes do produto inventadas
- produto girado ou em ângulo diferente
- adição de textos, preços ou elementos gráficos

Responda apenas gerando a imagem.
"""


PROMPT_JURI_LOTE_FINAL = """
Atue como um Diretor de Marketing sênior especialista em conversão para TikTok Shop.

Neste chat foram anexados {quantidade_videos} vídeos do produto "{nome_produto}".

Abaixo estão os roteiros originais e os contextos criativos usados na geração:

{contexto_roteiros}

Sua tarefa é assistir todos os vídeos e criar um ranking completo do melhor ao pior.

Critérios de avaliação:
- força de retenção nos primeiros segundos
- clareza visual
- fidelidade ao produto
- qualidade geral da execução
- potencial de conversão
- apelo de compra
- naturalidade visual
- ausência de glitches, deformações, terceira mão ou produto girado indevidamente

Para CADA vídeo, você deve informar:
- index_video: posição original do vídeo na ordem de anexação, começando em 0
- rank_pos: posição no ranking final
- gatilho: o principal gatilho mental despertado
- beneficio: o principal benefício prático percebido
- motivo: uma explicação curta em uma frase

Regras obrigatórias de saída:
- Inclua TODOS os vídeos sem exceção.
- Não pule nenhum vídeo.
- Não repita rank_pos.
- Não repita index_video.
- O melhor vídeo deve receber rank_pos 1.
- O pior vídeo deve receber rank_pos {quantidade_videos}.
- Retorne EXCLUSIVAMENTE um JSON puro, sem markdown, sem explicações e sem texto adicional. NÃO use blocos de código markdown (```json), devolva apenas a estrutura de lista JSON diretamente.

Formato exato:
[
  {{"index_video": 0, "rank_pos": 1, "gatilho": "Desejo", "beneficio": "Pele_Firme", "motivo": "Explicacao curta em uma frase."}},
  {{"index_video": 1, "rank_pos": 2, "gatilho": "Urgencia", "beneficio": "Tempo_Salvo", "motivo": "Explicacao curta em uma frase."}}
]
"""