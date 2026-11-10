// 예: 설명 영상 속 '실제 데이터베이스 관리 화면' — 손으로 그린 표 대신 디자인 시스템 컴포넌트로(2026-11-10 DB 인덱스 영상: 'DB 느낌이 안 난다')
import React from "react";
import { Table, pixel, proportional } from "@astryxdesign/core/Table";
import { Badge } from "@astryxdesign/core/Badge";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { VStack, HStack } from "@astryxdesign/core/Stack";
import { Card } from "@astryxdesign/core/Card";

interface Row extends Record<string, unknown> { id: number; customer: string; amount: string; status: string }
const rows: Row[] = [
  { id: 4241, customer: "손님 4240", amount: "12,000원", status: "배송 완료" },
  { id: 4242, customer: "손님 4242", amount: "38,500원", status: "배송 중" },
  { id: 4243, customer: "손님 1033", amount: "7,900원", status: "결제 완료" },
  { id: 4244, customer: "손님 4242", amount: "21,000원", status: "배송 중" },
  { id: 4245, customer: "손님 88", amount: "54,000원", status: "취소" },
];
const tone = (s: string): "error" | "warning" | "success" => (s === "취소" ? "error" : s === "배송 중" ? "warning" : "success");

export default function Scene() {
  return (
    <div style={{ padding: 48, height: "100%", boxSizing: "border-box" }}>
      <Card>
        <VStack gap={4}>
          <HStack gap={3}>
            <Heading level={2}>orders</Heading>
            <Badge label="1,000,000 rows" />
            <Badge variant="info" label="INDEX customer_id" />
          </HStack>
          <Text color="secondary">SELECT * FROM orders WHERE customer_id = 4242;</Text>
          <Table<Row> data={rows} idKey="id" density="balanced" isStriped
            columns={[
              { key: "id", header: "id", width: pixel(90) },
              { key: "customer", header: "customer", width: proportional(2) },
              { key: "amount", header: "amount", width: proportional(1), align: "end" },
              { key: "status", header: "status", width: proportional(1), renderCell: (r) => <Badge variant={tone(r.status)} label={r.status} /> },
            ]} />
        </VStack>
      </Card>
    </div>
  );
}
