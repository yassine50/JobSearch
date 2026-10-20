import tls from 'node:tls'
import net from 'node:net'
import dns from 'node:dns'
import crypto from 'node:crypto'

const RELAY_SECRET = process.env.SMTP_RELAY_SECRET || 'jobsearcher-smtp-relay-v1-2026'

function ipv4Lookup(hostname, options, callback) {
  return dns.lookup(hostname, { family: 4 }, callback)
}

function extractAddress(addr) {
  const s = String(addr || '').trim()
  const m = s.match(/<([^>]+)>/)
  return (m ? m[1] : s).trim()
}

function dotStuffMime(rawBuffer) {
  // Convert buffer to latin1/binary string so byte values are preserved 1:1
  let str = rawBuffer.toString('latin1')
  // Normalize all line endings to CRLF
  str = str.replace(/\r?\n/g, '\r\n')
  // RFC 5321 section 4.5.2 transparency: leading period on a line is doubled
  if (str.startsWith('.')) {
    str = '.' + str
  }
  str = str.replace(/\r\n\./g, '\r\n..')
  if (!str.endsWith('\r\n')) {
    str += '\r\n'
  }
  return Buffer.from(str + '.\r\n', 'latin1')
}

function createSmtpProtocol(socket, timeoutMs = 15000) {
  let buffer = ''
  let currentLines = []
  let pendingResolve = null
  let pendingReject = null
  let timer = null

  const clearTimer = () => {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  const failPending = (err) => {
    clearTimer()
    if (pendingReject) {
      const rej = pendingReject
      pendingResolve = null
      pendingReject = null
      rej(err)
    }
  }

  const processBuffer = () => {
    while (true) {
      const idx = buffer.indexOf('\n')
      if (idx === -1) break
      const line = buffer.slice(0, idx).replace(/\r$/, '')
      buffer = buffer.slice(idx + 1)
      currentLines.push(line)

      // RFC 5321: final line of response has 3 digits followed by space or EOL
      const m = line.match(/^(\d{3})(?: (.*)|$)/)
      if (m && pendingResolve) {
        const code = parseInt(m[1], 10)
        const fullText = currentLines.join('\n')
        currentLines = []
        clearTimer()
        const res = pendingResolve
        pendingResolve = null
        pendingReject = null
        res({ code, text: fullText })
        break
      }
    }
  }

  socket.on('data', (chunk) => {
    buffer += chunk.toString('utf8')
    processBuffer()
  })

  socket.on('error', (err) => {
    failPending(err)
  })

  socket.on('close', () => {
    failPending(new Error('SMTP connection closed unexpectedly'))
  })

  const readResponse = (stepTimeout = timeoutMs) =>
    new Promise((resolve, reject) => {
      pendingResolve = resolve
      pendingReject = reject
      timer = setTimeout(() => {
        failPending(new Error(`SMTP response timed out after ${stepTimeout}ms`))
      }, stepTimeout)
      processBuffer()
    })

  const sendCommand = async (cmdStr, expectedCodes = [250], stepTimeout = timeoutMs) => {
    const respPromise = readResponse(stepTimeout)
    socket.write(cmdStr + '\r\n', 'utf8')
    const resp = await respPromise
    if (expectedCodes && !expectedCodes.includes(resp.code)) {
      const err = new Error(`SMTP ${resp.code}: ${resp.text}`)
      err.smtpCode = resp.code
      throw err
    }
    return resp
  }

  const sendRawData = async (dataBuffer, expectedCodes = [250], stepTimeout = 25000) => {
    const respPromise = readResponse(stepTimeout)
    socket.write(dataBuffer)
    const resp = await respPromise
    if (expectedCodes && !expectedCodes.includes(resp.code)) {
      const err = new Error(`SMTP DATA ${resp.code}: ${resp.text}`)
      err.smtpCode = resp.code
      throw err
    }
    return resp
  }

  return { readResponse, sendCommand, sendRawData }
}

async function openAuthenticatedSmtp({ host, port, user, password }) {
  const cleanHost = String(host || 'smtp.gmail.com').trim()
  const cleanUser = extractAddress(user)
  const cleanPwd = String(password || '').replace(/\s+/g, '')

  // Connect via implicit TLS on 465 first (fastest & most reliable for Gmail),
  // or STARTTLS if a custom port != 465 && cleanHost != 'smtp.gmail.com' is used
  const useImplicitTls = cleanHost === 'smtp.gmail.com' || Number(port) === 465

  let socket
  let proto

  if (useImplicitTls) {
    socket = await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('TLS connect timeout (8s)')), 8000)
      const s = tls.connect(
        {
          host: cleanHost,
          port: 465,
          servername: cleanHost,
          lookup: ipv4Lookup,
        },
        () => {
          clearTimeout(t)
          resolve(s)
        }
      )
      s.once('error', (err) => {
        clearTimeout(t)
        reject(err)
      })
    })
    proto = createSmtpProtocol(socket)
    const greeting = await proto.readResponse(8000)
    if (greeting.code !== 220) {
      throw new Error(`Unexpected SMTP greeting: ${greeting.text}`)
    }
    await proto.sendCommand('EHLO cvtomatch.com', [250])
  } else {
    const rawSocket = await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('TCP connect timeout (8s)')), 8000)
      const s = net.connect(
        {
          host: cleanHost,
          port: Number(port) || 587,
          lookup: ipv4Lookup,
        },
        () => {
          clearTimeout(t)
          resolve(s)
        }
      )
      s.once('error', (err) => {
        clearTimeout(t)
        reject(err)
      })
    })
    const plainProto = createSmtpProtocol(rawSocket)
    const greeting = await plainProto.readResponse(8000)
    if (greeting.code !== 220) {
      throw new Error(`Unexpected SMTP greeting: ${greeting.text}`)
    }
    await plainProto.sendCommand('EHLO cvtomatch.com', [250])
    await plainProto.sendCommand('STARTTLS', [220])
    rawSocket.removeAllListeners('data')
    rawSocket.removeAllListeners('error')
    rawSocket.removeAllListeners('close')

    socket = await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('STARTTLS handshake timeout (8s)')), 8000)
      const tlsSock = tls.connect(
        {
          socket: rawSocket,
          servername: cleanHost,
        },
        () => {
          clearTimeout(t)
          resolve(tlsSock)
        }
      )
      tlsSock.once('error', (err) => {
        clearTimeout(t)
        reject(err)
      })
    })
    proto = createSmtpProtocol(socket)
    await proto.sendCommand('EHLO cvtomatch.com', [250])
  }

  // Authenticate via AUTH LOGIN
  try {
    await proto.sendCommand('AUTH LOGIN', [334])
    await proto.sendCommand(Buffer.from(cleanUser, 'utf8').toString('base64'), [334])
    await proto.sendCommand(Buffer.from(cleanPwd, 'utf8').toString('base64'), [235])
  } catch (authErr) {
    try { socket.destroy() } catch {}
    const e = new Error(
      `Gmail authentication failed (${authErr.message}). Please check your Gmail address and 16-character App Password in Settings.`
    )
    e.authError = true
    throw e
  }

  return { socket, proto, cleanUser }
}

export default async function handler(req, res) {
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Origin', '*')
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS')
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Relay-Key')
    return res.status(200).end()
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ ok: false, error: 'Method not allowed' })
  }

  const providedKey = req.headers['x-relay-key'] || ''
  const expectedKey = crypto
    .createHmac('sha256', RELAY_SECRET)
    .update('cvtomatch-smtp-dispatch')
    .digest('hex')

  if (providedKey !== expectedKey && providedKey !== RELAY_SECRET) {
    return res.status(401).json({ ok: false, error: 'Unauthorized relay request' })
  }

  const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {})
  const {
    smtp_host = 'smtp.gmail.com',
    smtp_port = 587,
    smtp_user = '',
    smtp_password = '',
    messages = [],
  } = body

  if (!smtp_user || !smtp_password) {
    return res.status(400).json({ ok: false, error: 'Missing smtp_user or smtp_password' })
  }
  if (!Array.isArray(messages) || messages.length === 0) {
    return res.status(400).json({ ok: false, error: 'No messages provided' })
  }

  let session
  try {
    session = await openAuthenticatedSmtp({
      host: smtp_host,
      port: smtp_port,
      user: smtp_user,
      password: smtp_password,
    })
  } catch (connErr) {
    return res.status(connErr.authError ? 401 : 502).json({
      ok: false,
      auth_error: Boolean(connErr.authError),
      error: connErr.message || 'Failed to connect to SMTP server',
    })
  }

  const { socket, proto, cleanUser } = session
  const results = []
  let sentCount = 0

  try {
    for (let i = 0; i < messages.length; i++) {
      const m = messages[i]
      const toEmail = extractAddress(m.to_email)
      if (!toEmail || !toEmail.includes('@')) {
        results.push({ index: i, to_email: m.to_email, status: 'failed', error: 'Invalid recipient address' })
        continue
      }
      try {
        const rawBytes = Buffer.from(m.raw_mime_b64 || '', 'base64')
        const dataPayload = dotStuffMime(rawBytes)

        await proto.sendCommand(`MAIL FROM:<${cleanUser}>`, [250])
        await proto.sendCommand(`RCPT TO:<${toEmail}>`, [250, 251])
        await proto.sendCommand('DATA', [354])
        await proto.sendRawData(dataPayload, [250])

        sentCount += 1
        results.push({ index: i, to_email: toEmail, status: 'sent' })
      } catch (msgErr) {
        results.push({
          index: i,
          to_email: toEmail,
          status: 'failed',
          error: msgErr.message || 'Failed to send message',
        })
        try {
          await proto.sendCommand('RSET', [250])
        } catch {
          // If connection dropped mid-batch, break so remaining items report failure cleanly
          for (let j = i + 1; j < messages.length; j++) {
            results.push({
              index: j,
              to_email: messages[j].to_email,
              status: 'failed',
              error: 'SMTP connection interrupted',
            })
          }
          break
        }
      }
    }
  } finally {
    try {
      await proto.sendCommand('QUIT', [221, 250], 2000)
    } catch {}
    try {
      socket.destroy()
    } catch {}
  }

  return res.status(200).json({
    ok: sentCount > 0,
    sent: sentCount,
    total: messages.length,
    results,
  })
}
