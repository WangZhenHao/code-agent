"use client"

import { useParams } from "next/navigation"
import './page.css'

import Left from "./left"
import Right from "./right"

const Client = () => {
    // 路由 /projects/[id] 的 id 就是后端的 session_id，也是 LangGraph 的 thread id
    const { id } = useParams<{ id: string }>()
    return <>
    <div className="h-screen flex">
        <Left sessionId={id} />
        <Right />
    </div>
    </>;
}

export default Client;
